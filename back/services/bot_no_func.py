import asyncio
from lib import utils
from bson.objectid import ObjectId

class Bot:
    def __init__(self, app):
        self.app = app

    async def tick_positions(self, API=False):
        bot = await self.app.db.bot.find_one()

        if bot["active"]:
            print(f'[{utils.current_readable_time()}]: Fetching Positions')

            # todo : filter if user followedLeaders key
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

                # if the mix are different, one leader has changed its positions
                if current_user_mix != latest_user_mix:
                    n_orders = 0
                    user_amounts = user["amounts"]

                    current_set, latest_set = set(current_user_mix.items()), set(latest_user_mix.items())
                    current_difference, last_difference = current_set.difference(latest_set), latest_set.difference(current_set)

                    for bag in last_difference:
                        symbol, amount = bag

                        if amount != 0:
                            # if the symbol is not in the current user mix, then it has been closed
                            if symbol not in current_user_mix:
                                try:
                                    # * CLOSE
                                    # close_response = self.app.binance.close_position(symbol, amount)

                                    live_position = self.app.db.live.find_one({"userId": user["_id"], "symbol": symbol})

                                    current_time = utils.current_time()
                                    live_position.update({
                                        "amount": 0,
                                        "value": 0,
                                        # "orders": live_position["orders"] + [close_response],
                                        "orders": live_position["orders"] + [{"position": "close", "symbol": symbol, "amount": 0}],
                                        "updatedAt": current_time,
                                        "closedAt": current_time,
                                    })

                                    await self.app.db.history.insert_one(live_position)

                                    await self.app.db.live.delete_one({"userId": user["_id"], "symbol": symbol})

                                    user_amounts.pop(symbol)
                                    n_orders += 1

                                    print(f'Closed Position: {symbol} - {amount}')

                                except Exception as e:
                                    print(e)
                                    # did not close so the amount is still present in the current user mix
                                    current_user_mix[symbol] = amount

                    # if they are mixes in the current difference, positions have been changed or opened
                    if len(current_difference) > 0:
                        leaders_weight = 0
                        user_account = self.app.binance.account_snapshot(user)
                        user_account_value = float(user_account["valueUSDT"])

                    for bag in current_difference:
                        symbol, amount = bag

                        if amount != 0:
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
                                    leaders_weight += weight

                                pool_leader = pool[leaderId]
                                leader_live_ratio = pool_leader["account"]["liveRatio"]
                                leader_share = weight / leaders_weight
                                # if the leader has the symbol in his amounts... calculate all the necessary stats to reproduce the shares
                                if symbol in pool_leader["amounts"].keys():
                                    user_share += leader_share * leader_live_ratio * pool_leader["shares"][symbol]

                                    # calculate the symbol price only once
                                    if leader_index == 0:
                                        symbol_price = abs(pool_leader["values"][symbol] / pool_leader["amounts"][symbol])

                                    leader_index += 1

                            amount = (user_account_value * user_share) / symbol_price
                            value = amount * symbol_price

                            # if the symbol is in the last mix, the position has changed
                            if symbol in latest_user_mix:
                                try:
                                    # * CHANGE
                                    last_amount = latest_user_mix[symbol]
                                    if amount > last_amount:
                                        to_open = amount - last_amount
                                        final_amount = self.truncate_amount(to_open, precision, symbol_price)
                                        binance_reponse = self.app.binance.open_position(symbol, final_amount)
                                    else:
                                        to_close = - last_amount - amount
                                        final_amount = self.truncate_amount(to_close, precision, symbol_price)
                                        binance_reponse = self.app.binance.close_postion(symbol, final_amount)

                                    await self.app.db.live.update_one({"userId": user["_id"], "symbol": symbol}, {"$set": {
                                        "updatedAt": utils.current_time(),
                                        # "orders": user["oders"] + [binance_reponse]
                                        "orders": user["oders"] + [{"position": "change", "symbol": symbol, "amount": final_amount}]
                                    }})
                                        
                                    user_amounts[symbol] += final_amount
                                    n_orders += 1
                                        
                                    print(f'Ajusted Position: {symbol} - {last_amount} to {amount}')

                                except Exception as e:
                                    print(e)
                                    current_user_mix[symbol] = last_amount

                            # if it is not, the position is new and has been opened
                            else:
                                try:
                                    # * OPEN
                                    final_amount = self.truncate_amount(amount, precision, symbol_price)

                                    # open_response = self.app.binance.open_position(symbol, final_amount)

                                    current_time = utils.current_time()
                                    await self.app.db.live.insert_one({
                                        "userId": user["_id"], 
                                        "symbol": symbol,
                                        "amount": amount,
                                        "value": value,
                                        # "orders": [open_response],
                                        "orders": [{"position": "open", "symbol": symbol, "amount": final_amount}],
                                        "createdAt": current_time,
                                        "updatedAt": current_time,
                                        "closedAt": None
                                    })

                                    user_amounts[symbol] += final_amount
                                    n_orders += 1

                                    print(f'Opened Position: {symbol} - {amount}')

                                except Exception as e:
                                    print(e)
                                    current_user_mix.pop(symbol)

                await self.app.db.users.update_one({"username": "root"}, {"$set": {"mix": current_user_mix, "amounts": user_amounts}})
                await self.app.db.bot.update_one({}, {"$set": {"precisions": bot["precisions"]}, "$inc": {"ticks": 1, "orders": n_orders}})

            await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}})

            if not API:
                await asyncio.sleep(bot["tickInterval"])


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
            return amount
        
        return -amount
    
