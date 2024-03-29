import asyncio

class Bot:
    def __init__(self, app):
        self.app = app

    async def tick_positions(self):
        while True:
            print('TICK POSITIONS')

            user = await self.app.db.users.find_one({"username": 'root'})
            bot = await self.app.db.bot.find_one()
            pool = {}
            latest_user_mix = user["mix"]
            current_user_mix = {}

            for leaderId in bot["activeLeaders"]:
                leader = await self.app.db.leaders.find_one({"_id": leaderId})
                await self.app.scrap.tick_positions(leader)
                pool[leader["_id"]] = leader
                leader_amounts = leader["amounts"]
                
            # todo for user in active users / for leader is user followed
                for symbol, amount in leader_amounts.items():
                    if symbol not in current_user_mix: 
                        current_user_mix[symbol] = 0

                    current_user_mix[symbol] += amount

            # todo for user in active users
            if current_user_mix != latest_user_mix:
                n_orders = 0
                user_amounts = user["amounts"]
                current_set, latest_set = set(current_user_mix.items()), set(latest_user_mix.items())
                current_difference, last_difference = current_set.difference(latest_set), latest_set.difference(current_set)

                for bag in last_difference:
                    symbol, amount = bag

                    if symbol not in bot["precisions"].keys():
                        bot["precisions"][symbol] = self.app.binance.get_asset_precision(symbol)
                    
                    precision = bot["precisions"][symbol]
                    
                    if amount != 0:
                        if symbol not in current_user_mix:
                            try:
                                print(f'{bag} CLOSED POSITION')
                                close_response = self.app.binance.close_position(symbol, amount)
                                print(close_response)
                                user_amounts.pop(symbol)
                            except Exception as e:
                                print(e)
                                current_user_mix[symbol] = amount
                            # self.app.binance.close_position()

                leader_ratio = 1 / len(bot["activeLeaders"])

                if len(current_difference) > 0:
                    user_account = self.app.binance.account_snapshot(user)
                    user_account_value = float(user_account["valueUSDT"])

                for bag in current_difference:
                    symbol, amount = bag

                    if symbol not in bot["precisions"].keys():
                        bot["precisions"][symbol] = self.app.binance.get_asset_precision(symbol)
                    
                    precision = bot["precisions"][symbol]

                    if amount != 0:
                        user_share = 0
                        index = 0

                        for leaderId in bot["activeLeaders"]:
                            if "account" not in pool[leader["_id"]].keys():
                                # self.app.scrap.cooldown()
                                pool[leader["_id"]]["account"] = await self.app.scrap.update_leader_stats(leader)

                            leader_live_ratio = pool[leader["_id"]]["account"]["liveRatio"]

                            if symbol in pool[leader["_id"]]["amounts"].keys():
                                leader_amount = pool[leader["_id"]]["amounts"][symbol]
                                leader_share = pool[leader["_id"]]["shares"][symbol]
                                symbol_value = pool[leader["_id"]]["values"][symbol]

                                user_share += leader_ratio * leader_live_ratio * leader_share

                                if index == 0:
                                    symbol_price = abs(symbol_value / leader_amount)

                                index += 1

                        # print('user_share, symbol_price')
                        # print(user_share, symbol_price)
                        amount = (user_account_value * user_share) / symbol_price
                        # value = amount * symbol_price
                        # print('amount, value')
                        # print(amount, value)

                        if symbol in latest_user_mix:
                            try:
                                print(f'{bag} CHANGED POSITION')
                                last_amount = latest_user_mix[symbol]
                                if amount > last_amount:
                                    to_open = amount - last_amount
                                    final_amount = self.truncate_amount(to_open, precision, symbol_price)
                                    binance_reponse = self.app.binance.open_position(symbol, final_amount)
                                else:
                                    to_close = - last_amount - amount
                                    final_amount = self.truncate_amount(to_close, precision, symbol_price)
                                    binance_reponse = self.app.binance.close_postion(symbol, final_amount)
                                
                                # await self.app.db.live.insert_one(binance_reponse)
                                user_amounts[symbol] += final_amount
                                n_orders += 1
                            except Exception as e:
                                print(e)
                                current_user_mix[symbol] = last_amount

                        else:
                            try:
                                print(f'{bag} NEW POSITION')
                                final_amount = self.truncate_amount(amount, precision, symbol_price)
                                open_response = self.app.binance.open_position(symbol, final_amount)
                                open_response["userId"] = user['username']
                                await self.app.db.live.insert_one(open_response)
                                user_amounts[symbol] = final_amount
                                n_orders += 1

                            except Exception as e:
                                print(e)
                                current_user_mix.pop(symbol)
                            # for leaderId in bot["activeLeaders"]:
                            #     position_ratio = 
                await self.app.db.users.update_one({"username": "root"}, {"$set": {"mix": current_user_mix, "amounts": user_amounts}})
                await self.app.db.bot.update_one({}, {"$set": {"precisions": bot["precisions"]}, "$inc": {"ticks": 1, "orders": n_orders}})

            await self.app.db.bot.update_one({}, {"$inc": {"ticks": 1}})

            await asyncio.sleep(30)


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
    
