import asyncio
from lib import utils
from bson.objectid import ObjectId
import traceback
import time

class Bot:
    def __init__(self, app):
        self.app = app

    async def tick_positions(self, API=False):
        bot = await self.app.db.bot.find_one()

        while bot["active"]:
            try:
                bot = await self.app.db.bot.find_one()
                print(f'[{utils.current_readable_time()}]: Fetching Positions')

                users = self.app.db.users.find()
                pool = {}
                dropped_leaders = []

                async for user in users:
                    current_user_mix = {}
                    leaders_total_weight = 0

                    for leaderId, weight in user["followedLeaders"].items():
                        if leaderId not in dropped_leaders and leaderId not in pool.keys():
                            leader = await self.app.db.leaders.find_one({"_id": ObjectId(leaderId)})
                            
                            await self.app.scrap.tick_positions(bot, leader)

                            if len(leader["amounts"].keys()) > 0:
                                pool[leaderId] = leader
                                leaders_total_weight += weight

                            else: 
                                if utils.current_time() - leader["updateTime"] > 3600000:
                                    await self.app.scrap.tick_leader(bot, leader)

                                if leader["positionShow"] == True and leader["status"] == "ACTIVE" and leader["initInvestAsset"] == "USDT":
                                    latest_position = await self.app.db.position_history.find_one(
                                            {"leaderId": leader["_id"]},
                                            sort=[('updateTime', -1)]
                                    )

                                    if latest_position != None and utils.current_time() - latest_position["updateTime"] < 1800000:
                                        pool[leaderId] = leader
                                        leaders_total_weight += weight

                                    elif leaderId not in dropped_leaders:
                                        dropped_leaders.append(leaderId)
                                        
                                elif leaderId not in dropped_leaders:
                                    dropped_leaders.append(leaderId)

                    for leaderId in user["followedLeaders"].keys():
                        if leaderId not in dropped_leaders:
                            leader = pool[leaderId]
                    
                            for symbol, amount in leader["amounts"].items():
                                if symbol not in current_user_mix:
                                    current_user_mix[symbol] = 0

                                current_user_mix[symbol] += amount

                    # if the mix are different, one leader has changed its positions
                    if current_user_mix != user["mix"]:
                        n_orders = 0

                        current_mix_set, latest_mix_set = set(current_user_mix.items()), set(user["mix"].items())
                        current_mix_difference, last_mix_difference = current_mix_set.difference(latest_mix_set), latest_mix_set.difference(current_mix_set)

                        for symbol, mix_amount in last_mix_difference:
                            if mix_amount != 0:
                                # if the symbol is not in the current user mix, then it has been closed
                                if symbol not in current_user_mix:
                                    try:
                                        # * CLOSE
                                        # Find the current symbol price
                                        price = float(self.app.binance.client.ticker_price(symbol)["price"])
                                        precision = bot["precisions"][symbol]

                                        if abs(user["amounts"][symbol]) * price < precision["minNotional"]:
                                            amount = precision["minQty"]
                                        
                                            if user["amounts"][symbol] < 0:
                                                amount = -amount

                                            await self.open_position(user, symbol, amount, precision, price)
                                            n_orders += 1

                                        await self.close_position(user, symbol, precision, price)
                                        n_orders += 1

                                    except Exception as e:
                                        current_user_mix[symbol] = mix_amount
                                        
                                        await self.handle_exception(user, e, 'close_position', symbol)

                                        continue

                        # if they are mixes in the current difference, positions have been changed or opened
                        if len(current_mix_difference) > 0:
                            self.app.binance.account_snapshot(user)
                            symbol_prices = {}

                        for symbol, mix_amount in current_mix_difference:
                            # print(user["liveAmounts"][symbol], mix_amount)
                            # print(abs(user["liveAmounts"][symbol] - mix_amount) / abs(user["liveAmounts"][symbol]))
                            
                            # if symbol not in user["liveAmounts"].keys() or abs(user["liveAmounts"][symbol] - mix_amount) / abs(user["liveAmounts"][symbol]) > 0.05:
                            if mix_amount != 0:
                                # we need to precision to calculate the formatted amounts to place the orders
                                if symbol not in bot["precisions"].keys():
                                    bot["precisions"][symbol] = self.app.binance.get_asset_precision(symbol)
                                
                                precision = bot["precisions"][symbol]
                                user_shares = 0

                                for leaderId, weight in user["followedLeaders"].items():
                                    if leaderId not in dropped_leaders:
                                        if "account" not in pool[leaderId].keys():
                                            # get the current balance and live ratio
                                            pool[leaderId]["account"] = await self.app.scrap.update_leader_stats(bot, leader)

                                        pool_leader = pool[leaderId]

                                        # if the leader has the symbol in his amounts... calculate all the necessary stats to reproduce the shares
                                        if symbol in pool_leader["amounts"].keys():
                                            leader_weight_share = weight / leaders_total_weight
                                            position_leverage_ratio = pool_leader["leverages"][symbol] / user["leverage"]

                                            user_share = leader_weight_share * pool_leader["account"]["liveRatio"] * pool_leader["shares"][symbol] * position_leverage_ratio * user["leverage"]

                                            if pool_leader["amounts"][symbol] > 0:
                                                user_shares += user_share
                                            else:
                                                user_shares -= user_share
                                            # calculate the symbol price only once
                                            if symbol not in symbol_prices.keys():
                                                symbol_prices[symbol] = abs(pool_leader["notionalValues"][symbol] / pool_leader["amounts"][symbol])

                                new_user_amount = (user["valueUSDT"] * user_shares) / symbol_prices[symbol]
                            
                                # if the symbol is in the last mix, the position has changed
                                if symbol in user["mix"]:
                                    try:
                                        # * CHANGE
                                        await self.change_position(user, symbol, new_user_amount, precision, symbol_prices[symbol])
                                        n_orders += 1

                                    except Exception as e:
                                        current_user_mix[symbol] = user["amounts"][symbol]

                                        await self.handle_exception(user, e, 'change_position', symbol)

                                        continue

                                # if it is not, the position is new and has been opened
                                else:
                                    try:
                                        # * OPEN
                                        await self.open_position(user, symbol, new_user_amount, precision, symbol_prices[symbol])
                                        n_orders += 1
                                    # TESTING
                                    # await self.change_position(user, symbol, amount * -1, precision, symbol_price, current_user["amounts"])
                                    # n_orders += 1
                                    # await self.close_position(user, symbol, current_user["amounts"][symbol], current_user["amounts"])
                                    # current_user_mix.pop(symbol)
                                    # n_orders += 1

                                    except Exception as e:
                                        current_user_mix.pop(symbol)

                                        await self.handle_exception(user, e, 'open_position', symbol)

                                        continue
                        # else:
                        #     print('DIFF NOT SUPERIOR TO 0.1')

                        user["positionsValue"] = sum(abs(value) for value in user["values"].values()) 
                        user["notionalValue"] = sum(user["notionalValues"].values())
                        user["liveRatio"] = user["notionalValue"] / user["valueUSDT"]

                        for symbol, notional_value in user["notionalValues"].items():
                            user["shares"][symbol] = notional_value / user["notionalValue"]

                        user["mix"] = current_user_mix

                        await self.app.db.users.replace_one({"username": "root"}, user)
                        await self.app.db.bot.update_one({}, {"$set": {"precisions": bot["precisions"]}, "$inc": {"orders": n_orders}})

                await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}})

                if not API:
                    await asyncio.sleep(bot["tickInterval"])

            except Exception as e:
                trace = traceback.format_exc()
                print(trace)

                await self.app.log.create(bot, 'ERROR', 'bot/tick_positions', 'TRADE',f'Error in tick_position - {e}', details=traceback)

                time.sleep(30)


    async def open_position(self, user, symbol, amount, precision, symbol_price):
            if user["collateralMarginLevel"] > 2:
                final_amount, final_value  = self.truncate_amount(amount, precision, symbol_price)
                open_response = await self.app.binance.open_position(user, symbol, final_amount)
                current_time = utils.current_time()

                await self.app.db.live.insert_one({
                    "userId": user["_id"], 
                    "symbol": symbol,
                    "amount": amount,
                    "value": final_value,
                    "orders": [open_response],
                    "createdAt": current_time,
                    "updatedAt": current_time,
                    "closedAt": None,
                    "PNL": 0
                })

                user["amounts"][symbol] = final_amount
                user["values"][symbol] = final_value
                user["notionalValues"][symbol] = abs(final_value) / user["leverage"]

                await self.app.log.create(user, 'INFO', 'bot/open_position', 'TRADE',f'Opened Position: {symbol} - {final_amount}', details=open_response)
            else:
                await self.app.log.create(user, 'INFO', 'bot/open_position', 'TRADE',f'Could Not Open Position: {symbol} - Margin Level: {user["collateralMarginLevel"]}', details={"collateralMarginLevel": user["collateralMarginLevel"]})

    async def change_position(self, user, symbol, new_amount, precision, symbol_price):
        last_amount = user["liveAmounts"][symbol]
        print('last_amount, new_amount')
        print(last_amount, new_amount)
        last_final_amount, _ = self.truncate_amount(last_amount, precision, symbol_price)
        new_final_amount, _ = self.truncate_amount(new_amount, precision, symbol_price)
        amount_diff, _ = self.truncate_amount(new_amount - last_amount, precision, symbol_price)
        diff_value = abs(new_amount - last_amount) * symbol_price 
        target_value = amount_diff * symbol_price 
        responses = []
        print('symbol, last_final_amount, new_final_amount, amount_diff')
        print(symbol, last_final_amount, new_final_amount, amount_diff)
        print('abs(amount_diff) / last_final_amount')
        print(abs(amount_diff) / last_final_amount)
        if diff_value > precision["minNotional"]:
            if (new_amount > 0 and last_amount > 0) or (new_amount < 0 and last_amount < 0):
                if new_amount > 0:
                    if amount_diff > 0:
                        print(f'Opening {amount_diff}')
                        open_response = await self.app.binance.open_position(user, symbol, amount_diff)
                        responses.append(open_response)
                    else:
                        print(f'Closing {amount_diff}')
                        close_response = self.app.binance.close_position(symbol, amount_diff)
                        responses.append(close_response)
                else:
                    if amount_diff > 0:
                        print(f'Closing {amount_diff}')
                        close_response = self.app.binance.close_position(symbol, amount_diff)
                        responses.append(close_response)
                    else:
                        print(f'Opening {amount_diff}')
                        open_response = await self.app.binance.open_position(user, symbol, amount_diff)
                        responses.append(open_response)
            else:
                print('SWITCH AMOUNT')
                print(f'Closing {last_final_amount}')
                close_response = self.app.binance.close_position(symbol, last_final_amount)
                responses.append(close_response)
                print(f'Opening {new_final_amount}')
                open_response = await self.app.binance.open_position(user, symbol, new_final_amount)
                responses.append(open_response)

            live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})
            await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": {
                "amount": new_final_amount,
                "value": target_value,
                "orders": live_position["orders"] + responses,
                "updatedAt": utils.current_time(),
            }})
            
            user["amounts"][symbol] = new_final_amount
            user["values"][symbol] = target_value
            user["notionalValues"][symbol] = abs(target_value) / user["leverage"]

            await self.app.log.create(user, 'INFO', 'bot/change_position', 'TRADE',f'Ajusted Position: {symbol} - {last_final_amount} to {new_final_amount}', details=responses)


    async def close_position(self, user, symbol, precision, symbol_price):
        last_amount = user["liveAmounts"][symbol]
        final_amount, _ = self.truncate_amount(last_amount, precision, symbol_price)

        close_response = self.app.binance.close_position(symbol, -final_amount)
        live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})
        current_time = utils.current_time()

        live_position.update({
            "amount": 0,
            "value": 0,
            "orders": live_position["orders"] + [close_response],
            "updatedAt": current_time,
            "closedAt": current_time,
        })

        await self.app.db.history.insert_one(live_position)
        await self.app.db.live.delete_one({"userId": user["_id"], "symbol": symbol})

        user["amounts"].pop(symbol)
        user["shares"].pop(symbol)
        user["values"].pop(symbol)
        user["notionalValues"].pop(symbol)

        await self.app.log.create(user, 'INFO', 'bot/close_position', 'TRADE',f'Closed Position: {symbol} - {last_amount}', details=close_response)


    def truncate_amount(self, amount, precision, price):
        asset_precision = precision["stepSize"].split('1')[0].count('0')

        positive = True
        if amount < 0:
            positive = False

        amount = abs(amount)

        if amount < precision["minQty"]:
            amount = precision["minQty"]

        while amount * price < precision["minNotional"] * 1.1:
            amount += float(precision["stepSize"])

        amount = round(amount, asset_precision)

        if positive:
            return amount, amount * price
        
        return -amount, -amount * price
    

    async def handle_exception(self, user, error, source, symbol):
        trace = traceback.format_exc()
        print(trace)

        await self.app.log.create(user, 'ERROR', f'bot/{source}', 'TRADE', f'Error Closing Position: {symbol} - {user["amounts"][symbol]} - {error}', details=trace)

  

