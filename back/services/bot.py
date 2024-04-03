import asyncio
from lib import utils
from bson.objectid import ObjectId
import traceback


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
                    latest_user_mix = user["mix"]

                    for leaderId in user["followedLeaders"].keys():
                        if leaderId not in pool.keys():
                            leader = await self.app.db.leaders.find_one({"_id": ObjectId(leaderId)})
                            await self.app.scrap.tick_positions(leader)
                            pool[leaderId] = leader
                        
                        leader = pool[leaderId]
                        
                        for symbol, amount in leader["amounts"].items():
                            if symbol not in current_user_mix: 
                                current_user_mix[symbol] = 0

                            current_user_mix[symbol] += amount
                    # print(pool)
                    # if the mix are different, one leader has changed its positions
                    if current_user_mix != latest_user_mix:
                        n_orders = 0
                        current_user_amounts = user["amounts"]
                        current_user_values = user["values"]
                        current_user_shares = user["shares"]

                        current_mix_set, latest_mix_set = set(current_user_mix.items()), set(latest_user_mix.items())
                        current_mix_difference, last_mix_difference = current_mix_set.difference(latest_mix_set), latest_mix_set.difference(current_mix_set)

                        for mix_bag in last_mix_difference:
                            symbol, mix_amount = mix_bag

                            if mix_amount != 0:
                                # if the symbol is not in the current user mix, then it has been closed
                                if symbol not in current_user_mix:
                                    try:
                                        # * CLOSE
                                        # Find the current symbol price
                                        current_price = float(self.app.binance.client.ticker_price(symbol)["price"])
                                        precision = bot["precisions"][symbol]

                                        if abs(current_user_amounts[symbol]) * current_price < precision["minNotional"]:
                                            amount = precision["minQty"]

                                            if current_user_amounts[symbol] < 0:
                                                amount = -amount

                                            await self.open_position(user, symbol, amount, precision, symbol_price, current_user_amounts, current_user_values, current_user_shares)

                                        await self.close_position(user, symbol, current_user_amounts, current_user_values, current_user_shares)
                                        n_orders += 1

                                    except Exception:
                                        # print(e)
                                        # did not close so the amount is still present in the current user mix
                                        current_user_mix[symbol] = mix_amount
                                        traceback.print_exc()
                                        continue

                        # if they are mixes in the current difference, positions have been changed or opened
                        if len(current_mix_difference) > 0:
                            leaders_total_weight = sum(user["followedLeaders"].values())
                            user_account = self.app.binance.account_snapshot(user)
                            user_account_value = float(user_account["valueUSDT"])

                        for mix_bag in current_mix_difference:
                            symbol, mix_amount = mix_bag

                            if mix_amount != 0:
                                # we need to precision to calculate the formatted amounts to place the orders
                                if symbol not in bot["precisions"].keys():
                                    bot["precisions"][symbol] = self.app.binance.get_asset_precision(symbol)
                                
                                precision = bot["precisions"][symbol]

                                user_share = 0
                                leader_index = 0

                                for leaderId, weight in user["followedLeaders"].items():
                                    if "account" not in pool[leaderId].keys():
                                        # get the current balance and live ratio
                                        pool[leaderId]["account"] = await self.app.scrap.update_leader_stats(leader)

                                    pool_leader = pool[leaderId]
                                    leader_live_ratio = pool_leader["account"]["liveRatio"]
                                    leader_weight_share = weight / leaders_total_weight
                                    # if the leader has the symbol in his amounts... calculate all the necessary stats to reproduce the shares
                                    if symbol in pool_leader["amounts"].keys():
                                        user_share += leader_weight_share * leader_live_ratio * pool_leader["shares"][symbol]

                                        # calculate the symbol price only once
                                        if leader_index == 0:
                                            symbol_price = pool_leader["notionalValues"][symbol] / abs(pool_leader["amounts"][symbol])

                                        leader_index += 1

                                new_user_amount = (user_account_value * user_share) / symbol_price

                                if mix_amount < 0:
                                    new_user_amount = -new_user_amount

                                # if the symbol is in the last mix, the position has changed
                                if symbol in latest_user_mix:
                                    try:
                                        # * CHANGE
                                        print(symbol_price)
                                        await self.change_position(user, symbol, new_user_amount, precision, symbol_price, current_user_amounts, current_user_values, current_user_shares)
                                        n_orders += 1

                                    except Exception:
                                        # print(e)
                                        # reset the amount to its previous value
                                        current_user_mix[symbol] = current_user_amounts[symbol]
                                        traceback.print_exc()
                                        continue

                                # if it is not, the position is new and has been opened
                                else:
                                    try:
                                        # * OPEN
                                        await self.open_position(user, symbol, new_user_amount, precision, symbol_price, current_user_amounts, current_user_values, current_user_shares)
                                        n_orders += 1

                                    # TESTING
                                    # await self.change_position(user, symbol, amount * -1, precision, symbol_price, current_user_amounts)
                                    # n_orders += 1
                                    # await self.close_position(user, symbol, current_user_amounts[symbol], current_user_amounts)
                                    # current_user_mix.pop(symbol)
                                    # n_orders += 1

                                    except Exception:
                                        # print(e)
                                        # could not open so the symbol is removed from the mix
                                        current_user_mix.pop(symbol)
                                        traceback.print_exc()
                                        continue
                        
                        await self.app.db.users.update_one({"username": "root"}, {"$set": {"mix": current_user_mix, "amounts": current_user_amounts, "values": current_user_values, "shares": current_user_shares}})
                        await self.app.db.bot.update_one({}, {"$set": {"precisions": bot["precisions"]}, "$inc": {"orders": n_orders}})

                await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}})

                if not API:
                    await asyncio.sleep(bot["tickInterval"])

            except Exception:
                # print(e)
                traceback.print_exc()
                pass

    async def change_position(self, user, symbol, amount, precision, symbol_price, user_amounts, user_values, user_shares):
        last_amount = user_amounts[symbol]
        print(f'[{utils.current_readable_time()}]: Ajusting Position: {symbol} - {last_amount}')
        live_position = await self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})

        if amount > last_amount:
            to_open = amount - last_amount
            final_amount, final_value = self.truncate_amount(to_open, precision, symbol_price)
            print(final_value)
            binance_reponse = self.app.binance.open_position(symbol, final_amount)
        else:
            to_close = last_amount - amount
            final_amount, final_value = self.truncate_amount(to_close, precision, symbol_price)
            print(final_value)
            binance_reponse = self.app.binance.close_position(symbol, final_amount)

        await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": {
            "amount": final_amount,
            "value": live_position["value"] + final_value,
            "orders": live_position["orders"] + [binance_reponse],
            "updatedAt": utils.current_time(),
        }})
            
        target_amount, target_value = self.truncate_amount(amount, precision, symbol_price)
        user_amounts[symbol] = target_amount
        user_values[symbol] = abs(target_value)
        user_shares[symbol] = abs(target_value) / user["account"]["valueUSDT"]

        print(f'[{utils.current_readable_time()}]: Ajusted Position: {symbol} - {last_amount} to {target_amount}')



    async def open_position(self, user, symbol, amount, precision, symbol_price, user_amounts, user_values, user_shares):
        final_amount, final_value  = self.truncate_amount(amount, precision, symbol_price)
        print(f'[{utils.current_readable_time()}]: Opening Position: {symbol} - {final_amount}')

        open_response = self.app.binance.open_position(symbol, final_amount)

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

        user_amounts[symbol] = final_amount
        user_values[symbol] = abs(final_value)
        user_shares[symbol] = abs(final_value) / user["account"]["valueUSDT"]

        print(f'[{utils.current_readable_time()}]: Opened Position: {symbol} - {final_amount}')


    async def close_position(self, user, symbol, user_amounts, user_values, user_shares):
        last_amount = user_amounts[symbol]
        print(f'[{utils.current_readable_time()}]: Closing Position: {symbol} - {last_amount}')
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

        user_amounts.pop(symbol)
        user_values.pop(symbol)
        user_shares.pop(symbol)

        print(f'[{utils.current_readable_time()}]: Closed Position: {symbol} - {last_amount}')


    def truncate_amount(self, amount, precision, price):
        asset_precision = precision["stepSize"].split('1')[0].count('0')

        positive = True
        if amount < 0:
            positive = False

        amount = abs(amount)

        if amount < precision["minQty"]:
            amount = precision["minQty"]

        while amount * price < precision["minNotional"]:
            amount += float(precision["stepSize"])

        amount = round(amount, asset_precision)

        if positive:
            return amount, amount * price
        
        return -amount, -amount * price

