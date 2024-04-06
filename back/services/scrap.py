import os
import requests
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS
from fake_useragent import UserAgent
from lib import utils
import traceback
import time

endpoints = {
    "positions" : {
        "path": 'public/future/copy-trade/lead-data/positions?portfolioId=%s', 
        "type": "simple",
        "params": {}
        },
    "performance" : {
        "path": 'public/future/copy-trade/lead-portfolio/performance?portfolioId=%s&timeRange=%s',
        "type": "simple",
        "params": {"timeRange": "90D"}
        },
    "detail" : {
        "path": 'friendly/future/copy-trade/lead-portfolio/detail?portfolioId=%s', 
        "type": "simple",
        "params": {}
    },
    "chart" : {
        "path": 'public/future/copy-trade/lead-portfolio/chart-data?portfolioId=%s&timeRange=%s&dataType=%s', 
        "type": "simple",
        "params": {"timeRange": "90D", "dataType": "ROI"}
    },
    "position_history" : {
        "path": 'public/future/copy-trade/lead-portfolio/position-history', 
        "type": "paginated",
        "params": {"pageNumber" : 1, "pageSize": 10}
    },
    "transfer_history" : {
        "path": 'public/future/copy-trade/lead-portfolio/transfer-history', 
        "type": "paginated",
        "params": {"pageNumber" : 1, "pageSize": 10}
    }
}


class Scrap:
    # ! todo : RETRIES, ERROR BOUNDARY
    def __init__(self, app):
        GATEWAY_HOST = 'https://www.binance.com'
        self.API_PATH = '/'.join([GATEWAY_HOST, 'bapi/futures/v1'])
        self.COOLDOWN = 0.2

        self.app = app
        self.gateway = ApiGateway(GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(GATEWAY_HOST, self.gateway)
        self.user_agent = UserAgent()

    def cooldown(self):
        # time.sleep(self.COOLDOWN)
        pass

    def gen_headers(self):
        headers = {'User-Agent':str(self.user_agent.random)}
        # print(headers)

        return headers
    # Requests
    
    def fetch_data(self, leaderId, endpointType, params={}):
        endpoint = endpoints[endpointType]
        # Filter out the empty params
        filtered_params = {}
        for default_key, default_value in endpoint['params'].items():
            if default_key in params.keys() and params[default_key] is not None:
                filtered_params[default_key] = params[default_key]
            else:
                filtered_params[default_key] = default_value

        if endpoint["type"] == 'simple':
            # Interpolate strings
            path = endpoint["path"] % (leaderId, *filtered_params.values())
            url = '/'.join([self.API_PATH, path])

            response = self.session.get(url, headers=self.gen_headers())

        if endpoint["type"] == 'paginated':
            url = '/'.join([self.API_PATH, endpoint["path"]])

            response = self.session.post(
                url,
                json={"portfolioId": leaderId} | filtered_params,
                headers=self.gen_headers()
                )

        return response

    def fetch_pages(self, leaderId, endpointType, params={}, page_number=1, result=[], latest_item=None, reference=None):
        response = self.fetch_data(leaderId, endpointType, {"pageNumber": page_number} | params).json()

        if response["success"]:
            response_data = response["data"]
            response_list = response_data["list"]

            if latest_item and reference:
                response_list = sorted(response_list, key=lambda x: x[reference], reverse=True)

                for item in response_list:
                    if item[reference] > latest_item[reference]:
                        result.append(item)
                    else:
                        # print({ "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result })
                        return { "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result }
            else:
                result = result + response_list
                pages_length = response_data["total"] // 10
                # If remainder, add another page
                if response_data["total"] % 10:
                    pages_length += 1

                if page_number <= pages_length:
                    next_page = page_number + 1
                    # self.cooldown()
                    return self.fetch_pages(leaderId, endpointType, params, next_page, result)

                else:
                    return { "success": True, "reason": "full", "message": f"Fetched all pages of {endpointType}", "data": result }
        
        else:
            return { "success": False, "message": f"Could not fetch page {page_number}/{pages_length} of {endpointType}" }

 
    # DB Injections
    async def create_leader(self, bot, leaderId):
        try:   
            detail_reponse = self.fetch_data(leaderId, "detail").json()

            if detail_reponse["success"]:
                detail_data = detail_reponse["data"]

            else:
                return { "success": False, "message": "Could not fetch Detail" }
            
            if detail_data["positionShow"] == True:
                # todo: update leader if fail reasons

                if detail_data["status"] != "ACTIVE":
                    return { "success": False, "message": "Leader is not Active" }

                if detail_data["initInvestAsset"] != "USDT":
                    return { "success": False, "message": "Leader is not using USDT" }
                
                leader_db = await self.app.db.leaders.find_one({"binanceId": leaderId})

                if leader_db:
                    leader = leader_db

                else:
                    leader = {
                            "binanceId": leaderId,
                            "profileUrl": f'https://www.binance.com/en/copy-trading/lead-details/{leaderId}',
                            "userId": detail_data["userId"],
                            "nickname": detail_data["nicknameTranslate"],
                            "avatarUrl": detail_data["avatarUrl"],
                            "status": detail_data["status"],
                            "initInvestAsset": detail_data["initInvestAsset"],
                            "positionShow": detail_data["positionShow"],
                            "updateTime": utils.current_time(),
                            "historicPNL": 0,
                            "transferBalance": 0,
                            "totalBalance": 0,
                            "liveRatio": 0,
                            "positionsValue": 0,
                            "positionsNotionalValue": 0,
                            "amounts": {},
                            "notionalValues": {},
                            "values": {},
                            "shares": {},
                            "leverages": {}
                        }
                    await self.app.db.leaders.insert_one(leader)

                # print(leader_db)

                # self.cooldown()
                await self.tick_positions(bot, leader)

                # self.cooldown()
                await self.update_leader_stats(bot, leader)
                
                #todo do not replace if nothing changed ?
                await self.app.db.leaders.update_one(
                    {"_id": leader["_id"]}, 
                    {"$set": leader}
                )
                
                # print(leader)
            else:
                return { "success": False, "message": "Leader is not sharing Positions" }

        except Exception as e:
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/create_leader', 'TRADE',f'Error in create_leader - {e}', details=trace)

            time.sleep(30)
            pass


    async def tick_leader(self, bot, leader):
        try:   
            detail_reponse = self.fetch_data(leader["binanceId"], "detail").json()

            if detail_reponse["success"]:
                detail_data = detail_reponse["data"]

                leader.update({
                    "status": detail_data["status"],
                    "initInvestAsset": detail_data["initInvestAsset"],
                    "positionShow": detail_data["positionShow"],
                    "updateTime": utils.current_time(),
                })


                await self.app.db.leaders.update_one(
                    {"_id": leader["_id"]}, 
                    {"$set": leader}
                )
            
        except Exception as e:
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/tick_leader', 'TRADE',f'Error in tick_leader - {e}', details=trace)

            time.sleep(30)
            pass

    async def update_leader_stats(self, bot, leader):
        try:
            await self.tick_position_history(bot, leader)

            # self.cooldown()
            await self.tick_transfer_history(bot, leader)
        
            total_balance = leader["historicPNL"] + leader["transferBalance"] + leader["positionsValue"]

            update = {
                "totalBalance": total_balance,
                "liveRatio": leader["positionsValue"] / total_balance,
                "updateTime": utils.current_time()
            }

            leader.update(update)

            await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

            return update
        except Exception as e:
            # print(e)
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/update_leader_stats', 'TRADE',f'Error in update_leader_stats - {e}', details=traceback)

            time.sleep(30)
    
    async def tick_transfer_history(self, bot, leader):
        try:
            latest_transfer = await self.app.db.transfer_history.find_one(
                    {"leaderId": leader["_id"]},
                    sort=[('time', -1)]
                )

            transfer_history_response = self.fetch_pages(leader["binanceId"], "transfer_history", reference='time', latest_item=latest_transfer)
            print('tick_transfer_history transfer_history_response')
            print(transfer_history_response)
            if transfer_history_response["success"]:
                transfer_history = transfer_history_response["data"]

                for transfer in transfer_history:
                    transfer["leaderId"] = leader["_id"]
                    transfer_type = transfer["transType"]

                    if transfer_type == "LEAD_INVEST" or transfer_type == "LEAD_DEPOSIT":
                        leader["transferBalance"] += float(transfer["amount"])

                    elif transfer_type == "LEAD_WITHDRAW":
                        leader["transferBalance"] -= float(transfer["amount"])

                    else:
                        print(f"WARNING! UNKNOWN TRANFER TYPE: {transfer_type}")

                if len(transfer_history) > 0:
                    await self.app.db.transfer_history.insert_many(transfer_history)

            return transfer_history_response
        
        except Exception as e:
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/tick_transfer_history', 'TRADE',f'Error in tick_transfer_history - {e}', details=trace)

            time.sleep(30)
            pass

    async def tick_position_history(self, bot, leader):
        try:
            latest_position = await self.app.db.position_history.find_one(
                {"leaderId": leader["_id"]},
                sort=[('updateTime', -1)]
            )
            position_history_response = self.fetch_pages(leader["binanceId"], "position_history", reference='updateTime', latest_item=latest_position)
            print(position_history_response)
            if position_history_response["success"]:
                new_position_history = position_history_response["data"]
                partially_closed_positions = await self.app.db.position_history.distinct('id', {'status': 'Partially Closed'})
                new_positions = []
                print('partially_closed_positions')
                print(partially_closed_positions)
                for position in new_position_history:
                    position["leaderId"] = leader["_id"]
                    print('position["id"], position["id"] in partially_closed_positions')
                    print(position["id"], position["id"] in partially_closed_positions)
                    if position["id"] in partially_closed_positions:
                        partially_closed_position = await self.app.db.position_history.find_one({"leaderId": leader["_id"], "id": position["id"]})
                        print('partially_closed_position')
                        print(partially_closed_position)
                        leader['historicPNL'] -= float(partially_closed_position["closingPnl"])

                        await self.app.db.position_history.replace_one({"leaderId": leader["_id"], "id": position["id"]}, position)
                    else:
                        leader['historicPNL'] += float(position["closingPnl"])
                        new_positions.append(position)

                if len(new_positions) > 0:
                    print('new_positions')
                    print(new_positions)
                    await self.app.db.position_history.insert_many(new_positions)
                
            return position_history_response
        
        except Exception as e:
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/tick_position_history', 'TRADE',f'Error in tick_position_history - {e}', details=trace)

            time.sleep(30)
            pass

    async def tick_positions(self, bot, leader):
        try:
            binanceId = leader["binanceId"]
            fetch_data_response = self.fetch_data(binanceId, "positions").json()

            if fetch_data_response["success"]:
                latest_amounts = leader["amounts"]
                positions_notional_value = 0
                positions_value = 0
                positions = []
                amounts = {}
                values = {}
                notional_values = {}
                shares = {}
                leverages = {}

                for position in fetch_data_response["data"]:
                    position_amount = float(position["positionAmount"])

                    if  position_amount != 0:
                        position["leaderId"] = leader["_id"]
                        leverage = position["leverage"]
                        notional_value = float(position["notionalValue"])
                        position_value = abs(notional_value / leverage)
                        # print(notional_value, position_value)
                        symbol = position["symbol"]

                        if symbol not in amounts: 
                            amounts[symbol] = 0
                            notional_values[symbol] = 0
                            values[symbol] = 0

                        amounts[symbol] += position_amount
                        notional_values[symbol] += notional_value
                        values[symbol] += position_value
                        leverages[symbol] = leverage

                        positions_notional_value += abs(notional_value)
                        positions_value += position_value
                        positions.append(position)
                # print(values)
                if amounts != latest_amounts:
                    current_set, last_set = set(amounts.items()), set(latest_amounts.items())
                    current_difference, last_difference = current_set.difference(last_set), last_set.difference(current_set)

                    for bag in last_difference:
                        symbol, amount = bag

                        if amount != 0:
                            if symbol not in amounts:
                                # print(f'{bag} CLOSED POSITION')
                                await self.app.db.positions.delete_one({"leaderId": leader["_id"], "symbol": symbol})

                    for bag in current_difference:
                        symbol, amount = bag

                        if amount != 0:
                            symbol_positions = [position for position in positions if position.get('symbol') == symbol]

                            if symbol in latest_amounts:
                                # print(f'{bag} CHANGED POSITION')
                                for symbol_position in symbol_positions:
                                    await self.app.db.positions.replace_one({"leaderId": leader["_id"], "id": symbol_position["id"]}, symbol_position)
                            else:
                                # print(f'{bag} NEW POSITION')
                                for symbol_position in symbol_positions:
                                    await self.app.db.positions.insert_one(symbol_position)

                for symbol, value in values.items():
                    shares[symbol] = value / positions_value

                update = {
                    "positionsValue": positions_value,
                    "positionsNotionalValue": positions_notional_value,
                    "amounts": amounts,
                    "notionalValues": notional_values,
                    "shares": shares,
                    "values": values,
                    "leverages": leverages
                    }
                # print(update)
                leader.update(update)

                await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

            return fetch_data_response
        
        except Exception as e:
            trace = traceback.format_exc()
            print(trace)

            await self.app.log.create(bot, 'ERROR', 'scrap/tick_positions', 'TRADE',f'Error in tick_positions - {e}', details=trace)

            time.sleep(30)
            pass
    # Lifecycle

    def cleanup(self):
        self.gateway.shutdown()
