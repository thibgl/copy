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

                async for user in users:
                    current_user_mix = {}

                    for leaderId in user["followedLeaders"].keys():
                        if leaderId not in pool.keys():
                            leader = await self.app.db.leaders.find_one({"_id": ObjectId(leaderId)})
                            await self.app.scrap.tick_positions(bot, leader)
                            pool[leaderId] = leader
                        
                        leader = pool[leaderId]
                        
                        for symbol, amount in leader["amounts"].items():
                            if symbol not in current_user_mix: 
                                current_user_mix[symbol] = 0

                            current_user_mix[symbol] += amount
                    # print(pool)
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

                                            await self.open_position(user, symbol, amount, precision, symbol_price)
                                            n_orders += 1

                                        await self.close_position(user, symbol)
                                        n_orders += 1

                                    except Exception as e:
                                        # print(e)
                                        # did not close so the amount is still present in the current user mix
                                        current_user_mix[symbol] = mix_amount
                                        
                                        trace = traceback.format_exc()
                                        print(trace)

                                        await self.app.log.create(user, 'ERROR', 'bot/close_position', 'TRADE',f'Error Closing Position: {symbol} - {user["amounts"][symbol]} - {e}', details=trace)

                                        continue

                        # if they are mixes in the current difference, positions have been changed or opened
                        if len(current_mix_difference) > 0:
                            leaders_total_weight = sum(user["followedLeaders"].values())
                            self.app.binance.account_snapshot(user)
       
                        print('current_mix_difference')
                        print(current_mix_difference)
                        for symbol, mix_amount in current_mix_difference:
                            if mix_amount != 0:
                                # we need to precision to calculate the formatted amounts to place the orders
                                if symbol not in bot["precisions"].keys():
                                    print('NO PRECISION, FETCHING')
                                    bot["precisions"][symbol] = self.app.binance.get_asset_precision(symbol)
                                
                                precision = bot["precisions"][symbol]

                                user_share = 0
                                leader_index = 0

                                for leaderId, weight in user["followedLeaders"].items():
                                    print('weight')
                                    print(weight)
                                    if "account" not in pool[leaderId].keys():
                                        # get the current balance and live ratio
                                        pool[leaderId]["account"] = await self.app.scrap.update_leader_stats(bot, leader)

                                    pool_leader = pool[leaderId]
                                    leader_live_ratio = pool_leader["account"]["liveRatio"]
                                    leader_weight_share = weight / leaders_total_weight
                                    leverage_ratio = pool_leader["leverages"][symbol] / user["leverage"]

                                    print('leader_weight_share, leader_live_ratio')
                                    print(leader_weight_share, leader_live_ratio)
                                    # if the leader has the symbol in his amounts... calculate all the necessary stats to reproduce the shares
                                    if symbol in pool_leader["amounts"].keys():
                                        if pool_leader["amounts"][symbol] > 0:
                                            user_share += leader_weight_share * leader_live_ratio * leverage_ratio * pool_leader["shares"][symbol] * user["leverage"]
                                        else:
                                            user_share -= leader_weight_share * leader_live_ratio * leverage_ratio * pool_leader["shares"][symbol] * user["leverage"]
                                        # calculate the symbol price only once
                                        if leader_index == 0:
                                            symbol_price = abs(pool_leader["notionalValues"][symbol] / pool_leader["amounts"][symbol])

                                        leader_index += 1

                                new_user_amount = (user["account"]["valueUSDT"] * user_share) / symbol_price

                                # if mix_amount < 0:
                                #     new_user_amount = -new_user_amount
                                print('new_user_amount, symbol_price')
                                print(new_user_amount, symbol_price)
                            
                                # if the symbol is in the last mix, the position has changed
                                if symbol in user["mix"]:
                                    try:
                                        # * CHANGE
                                        print('CHANGE')
                                        print(symbol_price)
                                        await self.change_position(user, symbol, new_user_amount, precision, symbol_price)
                                        n_orders += 1

                                    except Exception as e:
                                        # print(e)
                                        # reset the amount to its previous value
                                        current_user_mix[symbol] = user["amounts"][symbol]
                                        print(trace)

                                        await self.app.log.create(user, 'ERROR', 'bot/change_position', 'TRADE',f'Error Ajusting Position: {symbol} - {user["amounts"][symbol]} to {new_user_amount} - {e}', details=trace)

                                        continue

                                # if it is not, the position is new and has been opened
                                else:
                                    try:
                                        # * OPEN
                                        await self.open_position(user, symbol, new_user_amount, precision, symbol_price)
                                        n_orders += 1
                                    # TESTING
                                    # await self.change_position(user, symbol, amount * -1, precision, symbol_price, current_user["amounts"])
                                    # n_orders += 1
                                    # await self.close_position(user, symbol, current_user["amounts"][symbol], current_user["amounts"])
                                    # current_user_mix.pop(symbol)
                                    # n_orders += 1

                                    except Exception as e:
                                        # print(e)
                                        # could not open so the symbol is removed from the mix
                                        current_user_mix.pop(symbol)
                                        trace = traceback.format_exc()
                                        print(trace)

                                        await self.app.log.create(user, 'ERROR', 'bot/open_position', 'TRADE',f'Error Opening Position: {symbol} - {new_user_amount} - {e}', details=trace)

                                        continue
                        
                        user["notionalValue"] = sum(user["notionalValues"].values())
                        user["liveRatio"] = user["notionalValue"] / user["account"]["valueUSDT"]

                        for symbol, notional_value in user["notionalValues"].items():
                            user["shares"][symbol] = notional_value / user["notionalValue"]

                        user["mix"] = current_user_mix

                        await self.app.db.users.replace_one({"username": "root"}, user)
                        await self.app.db.bot.update_one({}, {"$set": {"precisions": bot["precisions"]}, "$inc": {"orders": n_orders}})

                await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}})

                if not API:
                    await asyncio.sleep(bot["tickInterval"])

            except Exception as e:
                # print(e)
                trace = traceback.format_exc()
                print(trace)

                await self.app.log.create(user, 'ERROR', 'bot/tick_position', 'TRADE',f'Error in tick_position - {e}', details=traceback)

                time.sleep(30)

    async def open_position(self, user, symbol, amount, precision, symbol_price):
            final_amount, final_value  = self.truncate_amount(amount, precision, symbol_price)
            open_response = self.app.binance.open_position(symbol, final_amount)
            current_time = utils.current_time()

            print(final_amount, final_value)

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
            user['positionsValue'] += abs(final_value)

            await self.app.log.create(user, 'INFO', 'bot/open_position', 'TRADE',f'Opened Position: {symbol} - {final_amount}', details=open_response)


    async def change_position(self, user, symbol, amount, precision, symbol_price):
        last_amount = user["amounts"][symbol]
        live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})
        print('amount, last_amount')
        print(amount, last_amount)
        print(live_position)
        if amount > last_amount:
            to_open = amount - last_amount
            print('to_open')
            print(to_open)
            final_amount, final_value = self.truncate_amount(to_open, precision, symbol_price)
            print(final_value)
            binance_reponse = self.app.binance.open_position(symbol, final_amount)
        else:
            to_close = last_amount - amount
            print('to_close')
            print(to_close)
            final_amount, final_value = self.truncate_amount(to_close, precision, symbol_price)
            print(final_value)
            binance_reponse = self.app.binance.close_position(symbol, final_amount)

        await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": {
            "amount": live_position["amount"] + final_amount,
            "value": live_position["value"] + final_value,
            "orders": live_position["orders"] + [binance_reponse],
            "updatedAt": utils.current_time(),
        }})
            
        target_amount, target_value = self.truncate_amount(amount, precision, symbol_price)
        print('target_amount')
        print(target_amount)
        user["amounts"][symbol] = target_amount
        user["values"][symbol] = target_value
        user["notionalValues"][symbol] = abs(target_value) / user["leverage"]
        user['positionsValue'] += final_value

        await self.app.log.create(user, 'INFO', 'bot/change_position', 'TRADE',f'Ajusted Position: {symbol} - {last_amount} to {target_amount}', details=binance_reponse)


    async def close_position(self, user, symbol):
        last_amount = user["amounts"][symbol]
        close_response = self.app.binance.close_position(symbol, last_amount)
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

        user['positionsValue'] -= abs(user["values"][symbol])
        user["amounts"].pop(symbol)
        user["shares"].pop(symbol)
        user["values"].pop(symbol)
        user["notionalValues"].pop(symbol)

        await self.app.log.create(user, 'INFO', 'bot/close_position', 'TRADE',f'Closed Position: {symbol} - {last_amount}', details=close_response)


    def truncate_amount(self, amount, precision, price):
        print('truncate_amount')
        print(amount, precision, price)
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
            print('amount, amount * price')
            print(amount, amount * price)
            return amount, amount * price
        
        print('-amount, -amount * price')
        print(-amount, -amount * price)
        return -amount, -amount * price

