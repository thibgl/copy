import os
import requests
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS
from fake_useragent import UserAgent
from lib import utils

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

    async def tick_leader(self, leaderId):
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
                        "nickname": detail_data["nickname"],
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
                        "values": {},
                        "shares": {},
                    }
                await self.app.db.leaders.insert_one(leader)

            print(leader_db)

            # self.cooldown()
            await self.tick_positions(leader)

            # self.cooldown()
            await self.update_leader_stats(leader)
            
            #todo do not replace if nothing changed ?
            await self.app.db.leaders.update_one(
                {"_id": leader["_id"]}, 
                {"$set": leader}
            )
            
            print(leader)
        else:
            return { "success": False, "message": "Leader is not sharing Positions" }
            
        # return {
        #     "success": True,
        #     "message": "Successfully scraped Leader",
        #     "data": {
        #         "leader": leader,
        #         "positions": positions_data["positions"],
        #         "position_history": position_history,
        #         "transfer_history": transfer_history
        #         }
        #     }

    async def update_leader_stats(self, leader):
        await self.tick_position_history(leader)

        # self.cooldown()
        await self.tick_transfer_history(leader)
    
        total_balance = leader["historicPNL"] + leader["transferBalance"] + leader["positionsValue"]

        update = {
            "totalBalance": total_balance,
            "liveRatio": leader["positionsValue"] / total_balance,
            "updateTime": utils.current_time()
        }

        leader.update(update)

        await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

        return update

    
    async def tick_transfer_history(self, leader):
        latest_transfer = await self.app.db.transfer_history.find_one(
                {"leaderId": leader["_id"]},
                sort=[('time', -1)]
            )

        fetch_pages_response = self.fetch_pages(leader["binanceId"], "transfer_history", reference='time', latest_item=latest_transfer)

        if fetch_pages_response["success"]:
            transfer_history = fetch_pages_response["data"]

            for transfer in transfer_history:
                transfer["leaderId"] = leader["_id"]
                transfer_type = transfer["transType"]

                if transfer_type == "LEAD_INVEST" or transfer_type == "LEAD_DEPOSIT":
                    leader["transferBalance"] += float(transfer["amount"])

                if transfer_type == "LEAD_WITHDRAW":
                    leader["transferBalance"] -= float(transfer["amount"])

                else:
                    print(f"WARNING! UNKNOWN TRANFER TYPE: {transfer_type}")

            if len(transfer_history) > 0:
                await self.app.db.transfer_history.insert_many(transfer_history)

        return fetch_pages_response


    async def tick_position_history(self, leader):
        latest_position = await self.app.db.position_history.find_one(
            {"leaderId": leader["_id"]},
            sort=[('updateTime', -1)]
        )
          
        fetch_pages_response = self.fetch_pages(leader["binanceId"], "position_history", reference='updateTime', latest_item=latest_position)

        if fetch_pages_response["success"]:
            position_history = fetch_pages_response["data"]

            for position in position_history:
                position["leaderId"] = leader["_id"]
                leader['historicPNL'] += float(position["closingPnl"])

            if len(position_history) > 0:
                await self.app.db.position_history.insert_many(position_history)
            
        return fetch_pages_response


    async def tick_positions(self, leader):
        binanceId = leader["binanceId"]
        fetch_data_response = self.fetch_data(binanceId, "positions").json()

        if fetch_data_response["success"]:
            latest_amounts = leader["amounts"]
            positions_notional_value = 0
            positions_value = 0
            positions = []
            amounts = {}
            notional_values = {}
            shares = {}

            for position in fetch_data_response["data"]:
                position_amount = float(position["positionAmount"])

                if  position_amount != 0:
                    position["leaderId"] = leader["_id"]
                    notional_value = abs(float(position["notionalValue"]))
                    symbol = position["symbol"]

                    if symbol not in amounts: 
                        amounts[symbol] = 0
                    if symbol not in notional_values: 
                        notional_values[symbol] = 0

                    amounts[symbol] += position_amount
                    notional_values[symbol] += float(position["notionalValue"])

                    positions_notional_value += notional_value
                    positions_value += notional_value / position["leverage"]
                    positions.append(position)

            if amounts != latest_amounts:
                current_set, last_set = set(amounts.items()), set(latest_amounts.items())
                current_difference, last_difference = current_set.difference(last_set), last_set.difference(current_set)

                for bag in last_difference:
                    symbol, amount = bag

                    if amount != 0:
                        if symbol not in amounts:
                            print(f'{bag} CLOSED POSITION')
                            await self.app.db.postions.delete_many({"leaderId": leader["_id"], "symbol": symbol})

                for bag in current_difference:
                    symbol, amount = bag

                    if amount != 0:
                        symbol_positions = [position for position in positions if position.get('symbol') == symbol]

                        if symbol in latest_amounts:
                            print(f'{bag} CHANGED POSITION')
                            for symbol_position in symbol_positions:
                                await self.app.db.positions.replace_one({"leaderId": leader["_id"], "id": symbol_position["id"]}, symbol_position)
                        else:
                            print(f'{bag} NEW POSITION')
                            for symbol_position in symbol_positions:
                                await self.app.db.positions.insert_one(symbol_position)

            for symbol, value in notional_values.items():
                shares[symbol] = value / positions_notional_value

            update = {
                "positionsValue": positions_value,
                "positionsNotionalValue": positions_notional_value,
                "amounts": amounts,
                "values": notional_values,
                "shares": shares
                }
            
            leader.update(update)

            await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

        return fetch_data_response

    # Lifecycle

    def cleanup(self):
        self.gateway.shutdown()
