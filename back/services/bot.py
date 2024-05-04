import asyncio
from lib import utils
from bson.objectid import ObjectId
import traceback
import time
import pandas as pd


NOTIONAL_SAFETY_RATIO = 1.05
USER_BOOST = 2

class Bot:
    def __init__(self, app):
        self.app = app

    async def tick(self, API=False):
        bot = await self.app.db.bot.find_one()

        start_time = utils.current_time()
        lifecycle = {
            "tick_boost": False,
            "reset_rotate": False
        }

        if bot["account"]["data"]["active"]:
            users = self.app.db.users.find()

            roster = pd.DataFrame(columns=["ID"])
            leader_mixes = pd.DataFrame()
            dropped_leaders = []

            async for user in users:
                try:
                    user_leaders = pd.DataFrame(user["leaders"]["data"])
                    
                    if user_leaders.size > 0:
                        leader_mixes = pd.DataFrame()

                        for binance_id, leader_weight in user_leaders.iterrows():
                            if binance_id not in roster.index.unique():
                                try:
                                    leader = await self.app.scrap.get_leader(bot, binance_id)

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

                        user_mix = pd.DataFrame(user["mix"]["data"]).to_dict()
                        user_mix_new = leader_mixes.groupby('symbol').agg('sum').to_dict() if len(leader_mixes) > 0 else {"BAG": {}}
                        user_mix_diff = [bag[0] for bag in set(user_mix_new["BAG"].items()).difference(set(user_mix["BAG"].items()))]
                        user_positions_new = roster[roster.index.isin(user_leaders.index)]

                        user_account, positions_closed, positions_opened, positions_changed, excess_pool = await self.app.binance.user_account_update(bot, user, user_positions_new, user_leaders, user_mix_diff, lifecycle)
                        user_account_update_success = await self.app.database.update(obj=user, update=user_account, collection='users')
                        # print(user_account)
                        # print(positions_closed.head())
                        # print(positions_opened.head())
                        # print(positions_changed.head())
                        # print(excess_pool.head())
                        if user_account_update_success:
                            await self.close_positions(bot, user, positions_closed, user_mix_new)
                            await self.change_positions(bot, user, positions_changed, user_mix_new)
                            await self.open_positions(bot, user, positions_opened, user_mix_new)
                            await self.set_stop_losses(bot, user, positions_opened, positions_changed)

                        if lifecycle["reset_rotate"]:
                            self.app.scrap.cleanup()
                            self.app.scrap.start()
                        
                        else:
                            await self.repay_debts(bot, excess_pool, user_mix_new)

                        if not lifecycle["tick_boost"] and not lifecycle["reset_rotate"]:
                            await self.app.scrap.update_leaders(bot, user)
                
                        user_account_close = await self.app.binance.user_account_close(bot, user, user_mix_new, dropped_leaders)
                        user_account_close_success = await self.app.database.update(obj=user, update=user_account_close, collection='users')
            
                #! faire le transfer de TP
                except Exception as e:
                    trace = traceback.format_exc()
                    print(trace)
                    await self.app.log.create(bot, user, 'ERROR', f'bot/tick', 'TICK', f'Error During Tick: {e}', details={"trace": trace})

                    continue

        if not API:
            end_time = (utils.current_time() - start_time) / 1000
            interval = bot["account"]["data"]["tick_boost"] if lifecycle["tick_boost"] else bot["account"]["data"]["tick_interval"]
            await asyncio.sleep(interval - end_time)
            await self.tick()


    async def repay_debts(self, bot, excess_pool, new_user_mix):
        if len(excess_pool) > 0:
            for symbol, position in excess_pool.iterrows():
                print(position)
                try:
                    await self.app.binance.repay_position(bot, symbol, position["free"], position["MIN_AMOUNT"], position["stepSize"])
                except Exception as e:
                    await self.handle_exception(bot, bot, e, 'repay_debts', symbol, position.to_dict(), new_user_mix)
                    continue


    async def close_positions(self, bot, user, closed_positions, new_user_mix):
        if len(closed_positions) > 0:
            for symbol, position in closed_positions.iterrows():
                # print(position)
                try:
                    await self.app.binance.close_position(bot, symbol, -position["netAsset_TRUNCATED"], position["MIN_AMOUNT"])
                    await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/FULL',f'Closed Position: {symbol} - {position["netAsset_TRUNCATED"]}', details=position.to_dict())
                except Exception as e:
                    await self.handle_exception(bot, user, e, 'close_positions', symbol, position.to_dict(), new_user_mix)
                    continue

    async def open_positions(self, bot, user, opened_positions, new_user_mix):
        if len(opened_positions) > 0:
            for symbol, position in opened_positions.iterrows():
                # print(position)
                try:
                    # print(position)
                    await self.app.binance.open_position(bot, symbol, position["TARGET_AMOUNT_TRUNCATED"], position["MIN_AMOUNT"])
                    await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/FULL',f'Opened Position: {symbol} - {position["TARGET_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                except Exception as e:
                    await self.handle_exception(bot, user, e, 'open_positions', symbol, position.to_dict(), new_user_mix)
                    continue
    
    async def change_positions(self, bot, user, changed_positions, new_user_mix):
        if len(changed_positions) > 0:
            for symbol, position in changed_positions.iterrows():
                # print(position)
                if position["SWITCH_DIRECTION"]:
                    if position["netAsset_PASS"] and position["TARGET_AMOUNT_PASS"]:
                        try:
                            await self.app.binance.close_position(bot, symbol, -position["netAsset_TRUNCATED"], position["MIN_AMOUNT"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/AJUST',f'Closed Position: {symbol} - {position["netAsset_TRUNCATED"]}', details=position.to_dict())
                            await self.app.binance.open_position(bot, symbol, position["TARGET_AMOUNT_TRUNCATED"], position["MIN_AMOUNT"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["TARGET_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        except Exception as e:
                            await self.handle_exception(bot, user, e, 'change_positions/full_ajust', symbol, position.to_dict(), new_user_mix)
                            continue

                    else:
                        try:
                            await self.app.binance.open_position(bot, symbol, position["DIFF_AMOUNT_TRUNCATED"], position["MIN_AMOUNT"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        except Exception as e:
                            await self.handle_exception(bot, user, e, 'change_positions/diff_ajust', symbol, position.to_dict(), new_user_mix)
                            continue
                else:
                    try:
                        if position["OPEN"]:
                            await self.app.binance.open_position(bot, symbol, position["DIFF_AMOUNT_TRUNCATED"], position["MIN_AMOUNT"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        else:
                            await self.app.binance.close_position(bot, symbol, position["DIFF_AMOUNT_TRUNCATED"], position["MIN_AMOUNT"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/AJUST',f'Closed Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                    except Exception as e:
                        await self.handle_exception(bot, user, e, 'change_positions/partial_ajust', symbol, position.to_dict(), new_user_mix)
                        continue
    
    async def set_stop_losses(self, bot, user, changed_positions, opened_positions):
        pass
    
    async def handle_exception(self, bot, user, error, source, symbol, log, new_user_mix):
        trace = traceback.format_exc()
        print(trace)

        if source != 'close_positions' and symbol in new_user_mix.keys():
            print(symbol)
            new_user_mix["BAG"].pop(symbol)
            
        await self.app.log.create(bot, user, 'ERROR', f'bot/{source}', 'TRADE', f'Error Setting Position: {symbol} - {error}', details={"trace": trace, "log": log})
  