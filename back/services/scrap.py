import os
import requests
import time
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS


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
    def __init__(self, app):
        self.app = app

        self.GATEWAY_HOST = 'https://www.binance.com'
        self.API_PATH = '/'.join([self.GATEWAY_HOST, 'bapi/futures/v1'])
        self.COOLDOWN = 0.2

        self.gateway = ApiGateway(self.GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)

    def cooldown(self):
        time.sleep(self.COOLDOWN)

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

            response = self.session.get(url)

        if endpoint["type"] == 'paginated':
            url = '/'.join([self.API_PATH, endpoint["path"]])

            response = self.session.post(
                url,
                json={"portfolioId": leaderId} | filtered_params
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
                        print({ "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result })
                        return { "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result }
            else:
                result = result + response_list
                pages_length = response_data["total"] // 10
                # If remainder, add another page
                if response_data["total"] % 10:
                    pages_length += 1

                if page_number <= pages_length:
                    next_page = page_number + 1
                    self.cooldown()
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
                        "updateTime": int(time.time() * 1000),
                        "historicPNL": 0,
                        "transferBalance": 0,
                        "totalBalance": 0,
                        "liveRatio": 0,
                        "positionsValue": 0,
                        "positionsNotionalValue": 0,
                        "mix": {},
                        "followedBy": []
                    }
                await self.app.db.leaders.insert_one(leader)

        else:
            return { "success": False, "message": "Could not fetch Detail" }
        
        if leader["positionShow"] == True:

            if leader["status"] != "ACTIVE":
                return { "success": False, "message": "Leader is not Active" }

            if leader["initInvestAsset"] != "USDT":
                return { "success": False, "message": "Leader is not using USDT" }

        else:
            return { "success": False, "message": "Leader is not sharing Positions" }


        # self.cooldown()
        # performance_response = self.fetch_data(leaderId, "performance").json()

        # if performance_response["success"] == True:
        #     performance = performance_response["data"]
        # else:
        #     return { "success": False, "message": "Could not fetch Performance" }
            
        self.cooldown()
        positions_response = self.tick_positions(leader)

        if positions_response["success"]:
            positions_data = positions_response["data"]
            if len(positions_data["positions"]) > 0:
                await self.app.db.positions.insert_many(positions_data["positions"])

        else:
            return { "success": False, "message": "Could not fetch Positions" }
                    
        self.cooldown()
        leader = self.tick_position_history(leader)

        self.cooldown()
        leader = self.tick_transfer_history(leader)
        
        leader["totalBalance"] = leader["historicPNL"] + leader["transferBalance"] + leader["liveValue"]
        leader["liveRatio"] = positions_data["positionsNotionalValue"] / leader["totalBalance"]

        # updated_stats = {
        #     "updateTime": int(time.time() * 1000),
        #     "totalBalance": total_balance,
        #     "liveRatio": live_ratio,
        #     "positionsValue": positions_data["positionsValue"],
        #     "positionsNotionalValue": positions_data["positionsNotionalValue"],
        #     "mix": positions_data["mix"]
        # }

        # await self.app.db.leaders.update_one(
        #     {"_id": leader["_id"]}, 
        #     {
        #         "$set": updated_stats
        #     }
        # )

        # leader.update(updated_stats)

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

            if len(transfer_history) > 0:
                await self.app.db.transfer_history.insert_many(transfer_history)

            return leader

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

            if fetch_pages_response["reason"] == 'full':
                if len(position_history) > 0:
                    await self.app.db.position_history.insert_many(position_history)

            if fetch_pages_response["reason"] == 'partial':
                pass
            
            return leader

        return fetch_pages_response


    def tick_positions(self, leader):
        binanceId = leader["binanceId"]
        positions_response = self.fetch_data(binanceId, "positions").json()

        if positions_response["success"]:
            portfolio_notional_value = 0
            portfolio_positions_value = 0
            positions = []
            mix = {}

            for position in positions_response["data"]:
                position_amount = float(position["positionAmount"])

                if  position_amount != 0:
                    position["leaderId"] = leader["_id"]
                    notional_value = abs(float(position["notionalValue"]))
                    symbol = position["symbol"]

                    if symbol not in mix: 
                        mix[symbol] = 0
                    mix[symbol] += position_amount

                    portfolio_notional_value += notional_value
                    portfolio_positions_value += notional_value / position["leverage"]
                    positions.append(position)
            
            return {"success": True, "message": f'Successfully scraped positions for {binanceId}', "data": {
                "positions": positions,
                "positionsValue": portfolio_positions_value,
                "positionsNotionalValue": portfolio_notional_value,
                "mix": mix
            }}
        
        return {"success": False, "message": f"Could not scrap postions for {binanceId}"}

    # Lifecycle

    def cleanup(self):
        self.gateway.shutdown()
