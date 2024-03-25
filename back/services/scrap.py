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
            print(url)

            response = self.session.get(url)

        if endpoint["type"] == 'paginated':
            url = '/'.join([self.API_PATH, endpoint["path"]])

            response = self.session.post(
                url,
                json={"portfolioId": leaderId} | filtered_params
                )

        return response

    def fetch_pages(self, leaderId, endpointType, params={}, page_number=1, result=[]):
        response = self.fetch_data(leaderId, endpointType, {"pageNumber": page_number} | params).json()

        if response["success"]:
            response_data = response["data"]

            pages_length = response_data["total"] // 10
            # If remainder, add another page
            if response_data["total"] % 10:
                pages_length += 1

            if page_number <= pages_length:
                result = result + response_data["list"]
                next_page = page_number + 1
                self.cooldown()
                return self.fetch_pages(leaderId, endpointType, params, next_page, result)

            else:
                return { "success": True, "message": f"Fetched all pages of {endpointType}", "data": result }
        
        else:
            return { "success": False, "message": f"Could not fetch page {page_number}/{pages_length} of {endpointType}" }

 
    # DB Injections

    def tick_leader(self, leaderId, update=True):
        detail_reponse = self.fetch_data(leaderId, "detail").json()

        if detail_reponse["success"]:
            detail_data = detail_reponse["data"]

            leader = {
                "leaderId": leaderId,
                "leaderUrl": f'https://www.binance.com/en/copy-trading/lead-details/{leaderId}',
                "userId": detail_data["userId"],
                "nickname": detail_data["nickname"],
                "avatarUrl": detail_data["avatarUrl"],
                "status": detail_data["status"],
                "initInvestAsset": detail_data["initInvestAsset"],
                "positionShow": detail_data["positionShow"],
                "updateTime": int(time.time() * 1000)
            }

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
            
        if update == False:

            self.cooldown()
            positions_response = self.fetch_data(leaderId, "positions").json()

            if positions_response["success"]:
                positions_data = positions_response["data"]
                positions_value = 0
                positions = []

                for position in positions_data:
                    if float(position["positionAmount"]) != 0:
                        position["leaderId"] = leaderId
                        positions_value += float(position["notionalValue"])
                        positions.append(position)

            else:
                return { "success": False, "message": "Could not fetch Positions" }
                        
            self.cooldown()
            historic_PNL = 0
            position_history_response = self.fetch_pages(leaderId, "position_history")

            if position_history_response["success"]:
                position_history = position_history_response["data"]
                for position in position_history:
                    position["leaderId"] = leaderId
                    historic_PNL += float(position["closingPnl"])

            else:
                return { "success": False, "message": "Could not fetch Positions History" }

            self.cooldown()
            transfer_balance = 0
            transfer_history_response = self.fetch_pages(leaderId, "transfer_history")

            if transfer_history_response["success"]:
                transfer_history = transfer_history_response["data"]

                for transfer in transfer_history:
                    transfer["leaderId"] = leaderId
                    transfer_type = transfer["transType"]

                    if transfer_type == "LEAD_INVEST" or transfer_type == "LEAD_DEPOSIT":
                        transfer_balance += float(transfer["amount"])

                    if transfer_type == "LEAD_WITHDRAW":
                        transfer_balance -= float(transfer["amount"])
            
            else:
                return { "success": False, "message": "Could not fetch Transfer History" }
            
            # leader = leader | performance
            leader["totalBalance"] = positions_value + transfer_balance + historic_PNL
            leader["liveRatio"] = positions_value / leader["totalBalance"]

        return {
            "success": True,
            "message": "Successfully scraped Leader",
            "data": {
                "leader": leader,
                "positions": positions,
                "position_history": position_history,
                "transfer_history": transfer_history
                }
            }

    def tick_positions(self, leaderId):
        positions = self.request_positions(leaderId)
        self.app.db.pool.insert_one(positions)

        return {leaderId, positions}

    # Lifecycle

    def cleanup(self):
        self.gateway.shutdown()
