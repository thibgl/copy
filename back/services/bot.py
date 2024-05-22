import asyncio
from lib import utils
from bson.objectid import ObjectId
import traceback
import time
import pandas as pd

class Bot:
    def __init__(self, app):
        self.app = app

    async def tick(self, tick, API=False):
        bot = await self.app.db.bot.find_one()

        start_time = utils.current_time()
        lifecycle = {
            "tick_boost": False,
            "reset_rotate": False
        }

        if bot["account"]["data"]["active"]:
            # print(tick["last_tick"])
            users = self.app.db.users.find()

            roster = pd.DataFrame(columns=["ID"])
            leader_mixes = pd.DataFrame()
            dropped_leaders = []

            async for user in users:
                try:
                    user_leaders = pd.DataFrame(user["leaders"]["data"])
                    
                    if user_leaders.size > 0:
                        leader_mixes = pd.DataFrame()
                        mean_unlevered_ratio = 0

                        for binance_id, leader_weight in user_leaders.iterrows():
                            if binance_id not in roster.index.unique():
                                try:
                                    leader = await self.app.scrap.get_leader(bot, binance_id)
                                    mean_unlevered_ratio += leader["account"]["data"]["average_unlevered_ratio"]

                                    if leader:
                                        positions_update, leader_grouped_positions = await self.app.scrap.leader_positions_update(bot, leader, lifecycle)

                                        if len(leader_grouped_positions) > 0:
                                            positions_update_success = await self.app.database.update(obj=leader, update=positions_update, collection='leaders')

                                            if positions_update_success:
                                                roster = pd.concat([roster, leader_grouped_positions]) if len(roster) > 0 else leader_grouped_positions

                                                leader_mix = leader_grouped_positions[["symbol", "positionAmount"]].rename(columns={"positionAmount": "BAG"})
                                                leader_mix["BAG"] = leader_mix["BAG"] * leader_weight["WEIGHT"]

                                                leader_mixes = pd.concat([leader_mixes, leader_mix]) if len(leader_mixes) > 0 else leader_mix
                                    else:
                                        dropped_leaders.append(binance_id)

                                except Exception as e:
                                    trace = traceback.format_exc()
                                    print(trace)
                                    continue

                        if len(leader_mixes) > 0 and not user["account"]["data"]["reset_mix"]:
                            user_mix_new = leader_mixes.groupby('symbol').agg('sum').to_dict()  
                        else:
                            user_mix_new = {"BAG": {}}
                        user_mix = pd.DataFrame(user["mix"]["data"]).to_dict()
                        user_mix_diff = [bag[0] for bag in set(user_mix_new["BAG"].items()).difference(set(user_mix["BAG"].items()))]
                        user_positions_new = roster[roster.index.isin(user_leaders.index)]

                        user_account, positions_closed, positions_opened, positions_changed, positions_excess, dropped_leaders, reset_mix = await self.app.binance.user_account_update(bot, user, user_positions_new, user_leaders, user_mix_diff, dropped_leaders, mean_unlevered_ratio, lifecycle)
                        user_account_update_success = await self.app.database.update(obj=user, update=user_account, collection='users')

                        if user_account_update_success:
                            await self.close_positions(bot, user, positions_closed, user_mix_new)
                            await self.change_positions(bot, user, positions_changed, user_mix_new)
                            await self.open_positions(bot, user, positions_opened, user_mix_new)
                            await self.repay_debts(bot, user, positions_excess)
                            await self.set_stop_losses(bot, user, positions_opened, positions_changed)
                        
                        if not lifecycle["tick_boost"] and not lifecycle["reset_rotate"]:
                            await self.app.scrap.update_leaders(bot, user)
                
                        user_account_close = await self.app.binance.user_account_close(bot, user, user_mix_new, dropped_leaders, reset_mix)
                        user_account_close_success = await self.app.database.update(obj=user, update=user_account_close, collection='users')
                        
                        last_tick = utils.current_time()
                        bot_update = {
                            "account": {
                                "last_tick": last_tick,
                                "ticks": bot["account"]["data"]["ticks"] + 1
                            }
                        }
                        await self.app.database.update(bot, bot_update, 'bot')
                        tick["last_tick"] = last_tick
                #! faire le transfer de TP
                except Exception as e:
                    try:
                        trace = traceback.format_exc()
                        print(trace)
                        await self.app.log.create(bot, user, 'FATAL', f'bot/tick', 'TICK', f'Error During Tick: {e}', details={"trace": trace})
                        raise SystemExit()
                    except:
                        raise SystemExit()

        if not API:
            end_time = (utils.current_time() - start_time) / 1000
            interval = bot["account"]["data"]["tick_boost"] if lifecycle["tick_boost"] else bot["account"]["data"]["tick_interval"]
            await asyncio.sleep(interval - end_time)
            await self.tick(tick)


    async def repay_debts(self, bot, user, positions_excess):
        if len(positions_excess) > 0:
            # print('positions_excess')
            # print(positions_excess)
            for symbol, position in positions_excess.iterrows():
                try:
                    await self.app.binance.repay_position(bot, user, symbol, position["free"], position)
                    time.sleep(0.2)
                except Exception as e:
                    print(e)
                    continue


    async def close_positions(self, bot, user, closed_positions, new_user_mix):
        if len(closed_positions) > 0:
            # print('closed_positions')
            # print(closed_positions)
            for asset, position in closed_positions.iterrows():
                try:
                    await self.app.binance.close_position(bot, user, asset, position["netAsset_TRUNCATED"], position, new_user_mix, 'FULL CLOSE', reverse=True)
                except:
                    continue

    async def open_positions(self, bot, user, opened_positions, new_user_mix):
        if len(opened_positions) > 0:
            # print('opened_positions')
            # print(opened_positions)
            for symbol, position in opened_positions.iterrows():
                try:
                    await self.app.binance.open_position(bot, user, symbol, position["TARGET_AMOUNT_TRUNCATED"], position, new_user_mix, 'FULL OPEN')
                except:
                    continue

    async def change_positions(self, bot, user, changed_positions, new_user_mix):
        if len(changed_positions) > 0:
            # print('changed_positions')
            # print(changed_positions)
            for symbol, position in changed_positions.iterrows():
                try:
                    if position["SWITCH_DIRECTION"]:
                        if position["netAsset_PASS"] and position["TARGET_AMOUNT_PASS"]:
                            await self.app.binance.close_position(bot, user, symbol, position["netAsset_TRUNCATED"], position, new_user_mix, 'FULL SWITCH CLOSE', reverse=True)
                            await self.app.binance.open_position(bot, user, symbol, position["TARGET_AMOUNT_TRUNCATED"], position, new_user_mix, 'FULL SWITCH OPEN')
                        else:
                            await self.app.binance.open_position(bot, user, symbol, position["DIFF_AMOUNT_TRUNCATED"], position, new_user_mix, 'PARTIAL SWITCH OPEN')
                    else:
                        if position["OPEN"]:
                            await self.app.binance.open_position(bot, user, symbol, position["DIFF_AMOUNT_TRUNCATED"], position, new_user_mix, 'PARTIAL OPEN')
                        else:
                            await self.app.binance.close_position(bot, user, symbol, position["DIFF_AMOUNT_TRUNCATED"], position, new_user_mix, 'PARTIAL CLOSE')
                except:
                    continue
    
    async def set_stop_losses(self, bot, user, changed_positions, opened_positions):
        pass
    
    async def handle_exception(self, bot, user, error, source, symbol, log):
        trace = traceback.format_exc()
        print(trace)
            
        await self.app.log.create(bot, user, 'ERROR', f'bot/{source}', 'TRADE', f'Error Setting Position: {symbol} - {error}', error=error, details={"trace": trace, "log": log})
  