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
        tick_boost = False

        if bot["account"]["data"]["active"]:
            # print(f'[{utils.current_readable_time()}]: Fetching Positions')

            users = self.app.db.users.find()

            roster = pd.DataFrame(columns=["ID"])
            leader_mixes = pd.DataFrame()

            async for user in users:
                try:
                    user_leaders = pd.DataFrame(user["leaders"]["data"])
                    
                    if user_leaders.size > 0:
                        leader_mixes = pd.DataFrame()

                        for binance_id, leader_weight in user_leaders.iterrows():
                            if binance_id not in roster.index.unique():
                                try:
                                    _, leader_grouped_positions = await self.app.scrap.get_leader(bot, user, binance_id=binance_id)

                                    if len(leader_grouped_positions) > 0:
                                        roster = pd.concat([roster, leader_grouped_positions]) if len(roster) > 0 else leader_grouped_positions
                                        leader_mix = leader_grouped_positions[["symbol", "positionAmount_SUM"]].rename(columns={"positionAmount_SUM": "BAG"})
                                        leader_mix["BAG"] = leader_mix["BAG"] * leader_weight["WEIGHT"]
                                        leader_mixes = pd.concat([leader_mixes, leader_mix]) if len(leader_mixes) > 0 else leader_mix
                                
                                except Exception as e:
                                    print(e)
                                    continue

                        user_mix = pd.DataFrame(user["mix"]["data"]).to_dict()

                        user_mix_new = leader_mixes.groupby('symbol').agg('sum').to_dict() if len(leader_mixes) > 0 else {"BAG": {}}
                        user_mix_diff = [bag[0] for bag in set(user_mix_new["BAG"].items()).difference(set(user_mix["BAG"].items()))]
                        user_positions_new = roster[roster.index.isin(user_leaders.index)]

                        user_account, positions_closed, positions_opened, positions_changed = await self.app.binance.user_account_update(bot, user, user_positions_new, user_leaders, user_mix_diff)
                        user_account_update_success = await self.app.database.update(obj=user, update=user_account, collection='users')

                        if user_account_update_success:
                            await self.close_positions(bot, user, positions_closed, user_mix_new)
                            await self.change_positions(bot, user, positions_changed, user_mix_new)
                            await self.open_positions(bot, user, positions_opened, user_mix_new)
                            await self.set_stop_losses(bot, user, positions_opened, positions_changed)

                        user_account_close = await self.app.binance.user_account_close(bot, user, user_mix_new)
                        user_account_close_success = await self.app.database.update(obj=user, update=user_account_close, collection='users')
            
                        tick_boost = any([len(positions_closed) > 0, len(positions_changed) > 0, len(positions_opened) > 0])

                #! faire le transfer de TP
                except Exception as e:
                    trace = traceback.format_exc()
                    await self.app.log.create(bot, user, 'ERROR', f'bot/tick', 'TICK', f'Error During Tick: {e}', details={"trace": trace})

                    continue

        if not API:
            end_time = (utils.current_time() - start_time) / 1000
            interval = bot["account"]["data"]["tick_boost"] if tick_boost else bot["account"]["data"]["tick_interval"]
            await asyncio.sleep(interval - end_time)
            await self.tick()


    async def close_positions(self, bot, user, closed_positions, new_user_mix):
        # print(closed_positions)
        # print("closed_positions")
        if len(closed_positions) > 0:
            for symbol, position in closed_positions.iterrows():
                print(position)
                try:
                    await self.app.binance.close_position(user, symbol, -position["netAsset_TRUNCATED"])
                    await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/FULL',f'Closed Position: {symbol} - {position["netAsset_TRUNCATED"]}', details=position.to_dict())
                except Exception as e:
                    await self.handle_exception(bot, user, e, 'close_positions', symbol, position.to_dict(), new_user_mix)
                    continue

    async def open_positions(self, bot, user, opened_positions, new_user_mix):
        # print("opened_positions")
        # print(opened_positions)
        if len(opened_positions) > 0:
            for symbol, position in opened_positions.iterrows():
                print(position)
                try:
                    # print(position)
                    await self.app.binance.open_position(user, symbol, position["TARGET_AMOUNT_TRUNCATED"])
                    await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/FULL',f'Opened Position: {symbol} - {position["TARGET_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                except Exception as e:
                    await self.handle_exception(bot, user, e, 'open_positions', symbol, position.to_dict(), new_user_mix)
                    continue
    
    async def change_positions(self, bot, user, changed_positions, new_user_mix):
        # print("changed_positions")
        # print(changed_positions)
        if len(changed_positions) > 0:
            for symbol, position in changed_positions.iterrows():
                print(position)
                if position["SWITCH_DIRECTION"]:
                    if position["netAsset_PASS"] and position["TARGET_AMOUNT_PASS"]:
                        print('double switch')
                        try:
                            print('close')
                            await self.app.binance.close_position(user, symbol, -position["netAsset_TRUNCATED"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/AJUST',f'Closed Position: {symbol} - {position["netAsset_TRUNCATED"]}', details=position.to_dict())
                            print('open')
                            await self.app.binance.open_position(user, symbol, position["TARGET_AMOUNT_TRUNCATED"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["TARGET_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        except Exception as e:
                            await self.handle_exception(bot, user, e, 'change_positions/full_ajust', symbol, position.to_dict(), new_user_mix)
                            continue

                    else:
                        print('simple switch')
                        try:
                            print('open')
                            await self.app.binance.open_position(user, symbol, position["DIFF_AMOUNT_TRUNCATED"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        except Exception as e:
                            await self.handle_exception(bot, user, e, 'change_positions/diff_ajust', symbol, position.to_dict(), new_user_mix)
                            continue
                else:
                    try:
                        if position["OPEN"]:
                            print('open')
                            await self.app.binance.open_position(user, symbol, position["DIFF_AMOUNT_TRUNCATED"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/AJUST',f'Opened Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                        else:
                            print('close')
                            await self.app.binance.close_position(user, symbol, position["DIFF_AMOUNT_TRUNCATED"])
                            await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/AJUST',f'Closed Position: {symbol} - {position["DIFF_AMOUNT_TRUNCATED"]}', details=position.to_dict())
                    except Exception as e:
                        await self.handle_exception(bot, user, e, 'change_positions/partial_ajust', symbol, position.to_dict(), new_user_mix)
                        continue
    
    async def set_stop_losses(self, bot, user, changed_positions, opened_positions):
        pass
    
    async def handle_exception(self, bot, user, error, source, symbol, log, new_user_mix):
        trace = traceback.format_exc()

        if source != 'close_positions':
            new_user_mix["BAG"].pop(symbol)
            
        await self.app.log.create(bot, user, 'ERROR', f'bot/{source}', 'TRADE', f'Error Setting Position: {symbol} - {error}', details={"trace": trace, "log": log})
    


                # start_time = utils.current_time()
            #    async for user in users:
            #         self.app.binance.account_snapshot(user)

            #         current_user_mix = {}
            #         leaders_total_weight = 0

            #         for leaderId, weight in user["followedLeaders"].items():
            #             if leaderId not in dropped_leaders and leaderId not in pool.keys():
            #                 leader = await self.app.db.leaders.find_one({"_id": ObjectId(leaderId)})
                            
            #                 await self.app.scrap.tick_positions(bot, leader)

            #                 if len(leader["amounts"].keys()) > 0:
            #                     pool[leaderId] = leader
            #                     leaders_total_weight += weight

            #                 else: 
            #                     if utils.current_time() - leader["updatedAt"] > 3600000:
            #                         await self.app.scrap.tick_leader(bot, leader)

            #                     if leader["positionShow"] == True and leader["status"] == "ACTIVE" and leader["initInvestAsset"] == "USDT":
            #                         latest_position = await self.app.db.position_history.find_one(
            #                                 {"leaderId": leader["_id"]},
            #                                 sort=[('updateTime', -1)]
            #                         )
            #                         # print(latest_position)
            #                         if latest_position != None and utils.current_time() - latest_position["updateTime"] < 1800000:
            #                             pool[leaderId] = leader
            #                             leaders_total_weight += weight

            #                         elif leaderId not in dropped_leaders:
            #                             dropped_leaders.append(leaderId)
                                        
            #                     elif leaderId not in dropped_leaders:
            #                         dropped_leaders.append(leaderId)
            #         n_leaders = 0
            #         for leaderId, weight in user["followedLeaders"].items():
            #             if leaderId not in dropped_leaders:
            #                 leader = pool[leaderId]
            #                 n_leaders += 1
                    
            #                 for symbol, amount in leader["amounts"].items():
            #                     if symbol not in current_user_mix:
            #                         current_user_mix[symbol] = 0

            #                     current_user_mix[symbol] += amount * weight / leaders_total_weight

            #         if user["reset"] == True:
            #             for symbol, value in user["mix"].items():
            #                 user["mix"][symbol] = value + 0.0000000001
            #         # if the mix are different, one leader has changed its positions
            #         if current_user_mix != user["mix"]:
            #             n_orders = 0
                        
            #             current_mix_set, latest_mix_set = set(current_user_mix.items()), set(user["mix"].items())
            #             current_mix_difference, last_mix_difference = current_mix_set.difference(latest_mix_set), latest_mix_set.difference(current_mix_set)

            #             for symbol, mix_amount in last_mix_difference:
            #                 if mix_amount != 0:
            #                     # if the symbol is not in the current user mix, then it has been closed
            #                     if symbol not in current_user_mix.keys():
            #                         # * CLOSE
            #                         # Find the current symbol price
            #                         symbol_price = float(self.app.binance.client.ticker_price(symbol)["price"])
            #                         precision = bot["precisions"][symbol]
            #                         new_amount = 0

            #                         log = {
            #                             "symbol": symbol,
            #                             "symbol_price": symbol_price,
            #                         }

            #                         if abs(user["liveAmounts"][symbol]) * symbol_price < precision["minNotional"] * NOTIONAL_SAFETY_RATIO:
            #                             new_amount = precision["minQty"]
                                    
            #                             if user["liveAmounts"][symbol] < 0:
            #                                 new_amount = -new_amount

            #                             await self.open_position(user, symbol, new_amount, precision, symbol_price, log, current_user_mix)
            #                             n_orders += 1

            #                         final_amount = user["liveAmounts"][symbol] + new_amount
            #                         await self.close_position(user, symbol, -final_amount, precision, symbol_price, log, current_user_mix)
            #                         n_orders += 1


            #             # if they are mixes in the current difference, positions have been changed or opened
            #             if len(current_mix_difference) > 0:
            #                 symbol_prices = {}

            #             for symbol, mix_amount in current_mix_difference:
            #                 if mix_amount != 0:
            #                     # we need to precision to calculate the formatted amounts to place the orders                             
            #                     precision = bot["precisions"][symbol]
            #                     user_shares = 0
            #                     leaders_log = []

            #                     for leaderId, leader_weight in user["followedLeaders"].items():
            #                         if leaderId not in dropped_leaders:
            #                             if "account" not in pool[leaderId].keys():
            #                                 # get the current balance and live ratio
            #                                 pool[leaderId]["account"] = await self.app.scrap.update_leader_stats(bot, pool[leaderId])

            #                             pool_leader = pool[leaderId]

            #                             # if the leader has the symbol in his amounts... calculate all the necessary stats to reproduce the shares
            #                             if symbol in pool_leader["amounts"].keys():
            #                                 leader_weight_share = leader_weight / leaders_total_weight
            #                                 # leader_position_leverage = pool_leader["leverages"][symbol]
            #                                 leader_live_ratio = pool_leader["account"]["liveRatio"]
            #                                 leader_share = pool_leader["shares"][symbol]
            #                                 user_leverage = user["leverage"]

            #                                 # position_leverage_ratio = leader_position_leverage / user_leverage
            #                                 user_share = leader_weight_share * leader_live_ratio * leader_share * user_leverage * USER_BOOST #* position_leverage_ratio

            #                                 if pool_leader["amounts"][symbol] > 0:
            #                                     user_shares += user_share
            #                                 else:
            #                                     user_shares -= user_share
            #                                 # calculate the symbol price only once
            #                                 if symbol not in symbol_prices.keys():
            #                                     symbol_prices[symbol] = abs(pool_leader["notionalValues"][symbol] / pool_leader["amounts"][symbol])

            #                                 leader_log = {
            #                                     "leaderId": leaderId,
            #                                     "nickname": pool_leader["nickname"],
            #                                     "binanceId": pool_leader["binanceId"],
            #                                     "user_share": user_share,
            #                                     "__user_leverage": user_leverage,
            #                                     "__leader_weight_share": leader_weight_share,
            #                                     "____leaders_total_weight": leaders_total_weight,
            #                                     "____leader_weight": leader_weight,
            #                                     "__USER_BOOST": USER_BOOST,
            #                                     # "_position_leverage_ratio": position_leverage_ratio,
            #                                     # "____leader_position_leverage": leader_position_leverage,
            #                                     "__leader_live_ratio": leader_live_ratio,
            #                                     "__leader_share": leader_share,
            #                                 }
            #                                 leaders_log.append(leader_log)

            #                     symbol_price = symbol_prices[symbol]
            #                     new_user_amount = (user["valueUSDT"] * user_shares) / symbol_price
            #                     log = {
            #                         "symbol": symbol,
            #                         "symbol_price": symbol_price,
            #                         "user_shares": user_shares,
            #                         "leaders_details": leaders_log
            #                     }

            #                     # if the symbol is in the last mix, the position has changed
            #                     if symbol in user["mix"].keys() or symbol in user["liveAmounts"].keys():
            #                         # * CHANGE
            #                         await self.change_position(user, symbol, new_user_amount, precision, symbol_prices[symbol], log, current_user_mix)
            #                         n_orders += 1

            #                     # if it is not, the position is new and has been opened
            #                     else:
            #                         # * OPEN
            #                         await self.open_position(user, symbol, new_user_amount, precision, symbol_prices[symbol], log, current_user_mix)
            #                         n_orders += 1
            #                         # TESTING
            #                         # await self.change_position(user, symbol, amount * -1, precision, symbol_price, current_user["amounts"])
            #                         # n_orders += 1
            #                         # await self.close_position(user, symbol, current_user["amounts"][symbol], current_user["amounts"])
            #                         # current_user_mix.pop(symbol)
            #                         # n_orders += 1

            #             user["positionsValue"] = sum(abs(value) for value in user["values"].values())
            #             user["notionalValue"] = sum(user["notionalValues"].values())
            #             user["liveRatio"] = user["notionalValue"] / user["valueUSDT"]

            #             for symbol, notional_value in user["notionalValues"].items():
            #                 user["shares"][symbol] = notional_value / user["notionalValue"]

            #             current_time = utils.current_time()
                        
            #             await self.app.db.users.update_one({"username": "root"}, {"$set": {
            #                 "mix": current_user_mix,
            #                 "positionsValue": user["positionsValue"],
            #                 "notionalValue": user["notionalValue"],
            #                 "liveRatio": user["liveRatio"],
            #                 "shares": user["shares"],
            #                 "updatedAt": current_time,
            #                 "reset": False
            #             }})

    #                    await self.app.db.bot.update_one({}, {"$set": {
    #                         "precisions": bot["precisions"]},
    #                         "$inc": {"orders": n_orders},
    #                         "$set": {"updatedAt": current_time}
    #                     })

    #             await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}, "$set": {"updatedAt": utils.current_time()}})

    #             if not API:
    #                 end_time = (utils.current_time() - start_time) / 1000
    #                 await asyncio.sleep(bot["tickInterval"] - end_time)

    #         except Exception as e:
    #             trace = traceback.format_exc()
    #             print(trace)

    #             await self.app.log.create(bot, bot, 'ERROR', 'bot/tick_positions', 'TRADE',f'Error in tick_position - {e}', details=traceback)

    #             time.sleep(bot["tickInterval"])


    # async def open_position(self, user, symbol, new_amount, precision, symbol_price, log, current_user_mix):
    #     try:
    #         last_amount = 0
    #         notional_pass = True

    #         if symbol in user["liveAmounts"].keys():
    #             last_amount = user["liveAmounts"][symbol]

    #         amount_diff = new_amount - last_amount
    #         diff_value = abs(amount_diff) * symbol_price 
            
    #         if diff_value < precision["minNotional"] * NOTIONAL_SAFETY_RATIO:
    #             notional_pass = False

    #         if notional_pass:
    #             if user["collateralMarginLevel"] > 1.25:
    #                 final_amount, final_value  = self.truncate_amount(new_amount, precision, symbol_price)
    #                 current_time = utils.current_time()
    #                 notional_value = abs(final_value) / user["leverage"]

    #                 position = {
    #                     "userId": user["_id"], 
    #                     "symbol": symbol,
    #                     "amount": new_amount,
    #                     "value": final_value,
    #                     "updatedAt": current_time,
    #                     "closedAt": None,
    #                     "PNL": 0
    #                 }

    #                 open_response = await self.app.binance.open_position(user, symbol, final_amount)

    #                 if open_response:
    #                     fully_opened = last_amount == 0

    #                     if fully_opened:
    #                         position.update({"createdAt": current_time, "orders": [open_response]})
    #                         await self.app.db.live.insert_one(position)
    #                     else:
    #                         live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})
    #                         position.update({"orders": live_position["orders"] + [open_response]})
    #                         await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": position})

    #                     user["amounts"][symbol] = final_amount
    #                     user["values"][symbol] = final_value
    #                     user["notionalValues"][symbol] = notional_value

    #                     await self.app.db.users.update_one({"_id": user["_id"]}, {"$set": {
    #                         "updatedAt": current_time,
    #                         "amounts": user["amounts"],
    #                         "values": user["values"],
    #                         "notionalValues": user["notionalValues"]
    #                     }})

    #                     log.update({
    #                         "type": "OPEN",
    #                         "full": fully_opened,
    #                         "amount": new_amount,
    #                         "final_amount": final_amount,
    #                         "final_value": final_value,
    #                         "response": open_response
    #                     })
            
    #                     if fully_opened:
    #                         await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/FULL',f'Opened Position: {symbol} - {final_amount}', details=log)
    #                     else:
    #                         await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/PARTIAL',f'Partially Opened Position: {symbol} - {last_amount} -> {last_amount + final_amount}', details=log)

    #                 else:
    #                     await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/REJECT',f'Could Not Open Position: {symbol} - Margin Level: {user["collateralMarginLevel"]}', details={"collateralMarginLevel": user["collateralMarginLevel"]})
                    
    #                 return True 
                  
    #         else:
    #             if symbol in user["mix"].keys():
    #                 current_user_mix[symbol] = user["mix"][symbol]
    #             # await self.app.log.create(bot, user, 'INFO', 'bot/open_position', 'TRADE/REJECT',f'Did Not Open Position: {symbol} - Notional Difference: {diff_value}', notify=False, insert=False)
                
    #             return False
            
    #     except Exception as e:
    #         current_user_mix[symbol] = user["mix"][symbol]
    #         await self.handle_exception(bot, user, e, 'open_position', symbol, log, current_user_mix)
            
    #         return False


    # async def close_position(self, user, symbol, new_amount, precision, symbol_price, log, current_user_mix):
    #     try:
    #         last_amount = 0
    #         notional_pass = True

    #         if symbol in user["liveAmounts"].keys():
    #             last_amount = user["liveAmounts"][symbol]

    #         amount_diff = new_amount - last_amount
    #         diff_value = abs(amount_diff) * symbol_price 
            
    #         if diff_value < precision["minNotional"] * NOTIONAL_SAFETY_RATIO:
    #             notional_pass = False

    #         if notional_pass:
    #             final_amount, final_value = self.truncate_amount(new_amount, precision, symbol_price)
    #             live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})
    #             current_time = utils.current_time()
            
    #             live_position.update({
    #                 "amount": 0,
    #                 "value": 0,
    #                 "updatedAt": current_time,
    #             })

    #             close_response = await self.app.binance.close_position(user, symbol, final_amount)

    #             if close_response:
    #                 live_position.update({"orders": live_position["orders"] + [close_response]})
    #                 fully_closed = symbol not in current_user_mix.keys()

    #                 if fully_closed:
    #                     live_position.update({"closedAt": current_time})
    #                     await self.app.db.history.insert_one(live_position)
    #                     await self.app.db.live.delete_one({"userId": user["_id"], "symbol": symbol})

    #                     user["amounts"].pop(symbol)
    #                     user["shares"].pop(symbol)
    #                     user["values"].pop(symbol)
    #                     user["notionalValues"].pop(symbol)

    #                     if symbol in user["liveAmounts"].keys():
    #                         user["liveAmounts"][symbol] = 0
    #                 else:
    #                     await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": live_position})

    #                 await self.app.db.users.update_one({"_id": user["_id"]}, {"$set": {
    #                     "updatedAt": current_time,
    #                     "amounts": user["amounts"],
    #                     "liveAmounts": user["liveAmounts"],
    #                     "values": user["values"],
    #                     "shares": user["shares"],
    #                     "notionalValues": user["notionalValues"]
    #                 }})
                    
    #                 log.update({
    #                     "type": "CLOSE",
    #                     "full": fully_closed,
    #                     "amount": new_amount,
    #                     "final_amount": final_amount,
    #                     "final_value": final_value,
    #                     "response": close_response
    #                 })
                
    #                 if fully_closed:
    #                     await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/FULL',f'Closed Position: {symbol} - {final_amount}', details=log)
    #                 else:
    #                     await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/PARTIAL',f'Partially Closed Position: {symbol} - {last_amount} -> {last_amount + final_amount}', details=log)
            
    #                 return True 

    #         else:
    #             if symbol in user["mix"].keys():
    #                 current_user_mix[symbol] = user["mix"][symbol]
    #             # await self.app.log.create(bot, user, 'INFO', 'bot/close_position', 'TRADE/REJECT',f'Did Not Close Position: {symbol} - Notional Difference: {diff_value}', notify=False, insert=False)
                
    #             return False
            
    #     except Exception as e:
    #         current_user_mix[symbol] = user["mix"][symbol]
    #         await self.handle_exception(bot, user, e, 'close_position', symbol, log, current_user_mix)
            
    #         return False
     


    # async def change_position(self, user, symbol, new_amount, precision, symbol_price, log, current_user_mix):
    #     try:
    #         last_amount = user["liveAmounts"][symbol]
    #         amount_diff = new_amount - last_amount
    #         diff_value = abs(amount_diff) * symbol_price 

    #         if diff_value > precision["minNotional"] * NOTIONAL_SAFETY_RATIO:
    #             if (new_amount > 0 and last_amount > 0) or (new_amount < 0 and last_amount < 0):
    #                 if new_amount > 0:
    #                     if amount_diff > 0:
    #                         await self.open_position(user, symbol, amount_diff, precision, symbol_price, log, current_user_mix)
    #                     else:
    #                         await self.close_position(user, symbol, amount_diff, precision, symbol_price, log, current_user_mix)
    #                 else:
    #                     if amount_diff > 0:
    #                         await self.close_position(user, symbol, amount_diff, precision, symbol_price, log, current_user_mix)
    #                     else:
    #                         await self.open_position(user, symbol, amount_diff, precision, symbol_price, log, current_user_mix)

    #             else:
    #                 opened = False
    #                 closed = await self.close_position(user, symbol, -last_amount, precision, symbol_price, log, current_user_mix)
    #                 if closed:
    #                     opened = await self.open_position(user, symbol, new_amount, precision, symbol_price, log, current_user_mix)
    #                 if not closed or not opened:
    #                     await self.app.log.create(bot, user, 'WARNING', 'bot/change_position', 'TRADE/INCOMPLETE',f'Did Not Switch Position: {symbol} - Closed: {-last_amount} {closed} -> Opened: {new_amount} {opened}', notify=False, insert=True)
    #                 # user["amounts"][symbol] = new_final_amount
    #                 # user["values"][symbol] = target_value
    #                 # user["notionalValues"][symbol] = abs(target_value) / user["leverage"]
    #     except Exception as e:
    #         if symbol in user["mix"].keys():
    #             current_user_mix[symbol] = user["mix"][symbol]
    #         await self.handle_exception(bot, user, e, 'change_position', symbol, log, current_user_mix)