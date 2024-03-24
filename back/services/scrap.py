import os
import requests
import time
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS

endpoints = {
    "positions" : {
        "path": 'lead-data/positions?portfolioId=%s', 
        "type": "simple",
        "params": {}
        },
    "performance" : {
        "path": 'lead-portfolio/performance?portfolioId=%s&timeRange=%s',
        "type": "simple",
        "params": {"timeRange": "90D"}
        },
    "detail" : {
        "path": 'lead-portfolio/detail?portfolioId=%s&timeRange=%s', 
        "type": "simple",
        "params": {"timeRange": "90D"}
    },
    "chart" : {
        "path": 'lead-portfolio/chart-data?portfolioId=%s&timeRange=%s&dataType=%s', 
        "type": "simple",
        "params": {"timeRange": "90D", "dataType": "ROI"}
    },
    "position_history" : {
        "path": 'lead-portfolio/position-history', 
        "type": "paginated",
        "params": {"pageNumber" : 1, "pageSize": 10}
    },
    "transfer_history" : {
        "path": 'lead-portfolio/transfer-history', 
        "type": "paginated",
        "params": {"pageNumber" : 1, "pageSize": 10}
    }
}


class Scrap:
    def __init__(self, app):
        self.app = app

        self.RAPID_API_KEY = os.environ.get('RAPID_API_KEY')
        self.RAPID_API_HOST = os.environ.get('RAPID_API_HOST')
        self.PUBLIC_API_HOST = 'www.binance.com/bapi/futures/v1/public/future/copy-trade'
        self.COOLDOWN = 0.2
        self.GATEWAY_HOST = 'https://www.binance.com'
        self.API_PATH = '/'.join([self.GATEWAY_HOST, 'bapi/futures/v1/public/future/copy-trade'])

        self.gateway = ApiGateway(self.GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)

    # Requests
    
    def request_data(self, portfolioId, dataType, params={}):
        endpoint = endpoints[dataType]
        # Filter out the empty params
        filtered_params = {}
        for key, default_value in endpoint['params'].items():
            value = params[key]
            if value is not None:
                filtered_params[key] = params[key]
            else:
                filtered_params[key] = default_value

        if endpoint["type"] == 'simple':
            # Interpolate strings
            path = endpoint["path"] % (portfolioId, *filtered_params.values())
            url = '/'.join([self.API_PATH, path])

            response = self.session.get(url)

        if endpoint["type"] == 'paginated':
            url = '/'.join([self.API_PATH, endpoint["path"]])
            print({"portfolioId": portfolioId} | filtered_params)
            response = self.session.post(
                url,
                json={"portfolioId": portfolioId} | filtered_params
                )

        return response
    
    # DB Injections

    def tick_leader(self, portfolioUrl, update=True):
        portfolioId = self.extractPortfolioId(portfolioUrl)

        details = self.request_details(portfolioId)
        self.app.db.leaders.insert_one(details)

        performance = self.request_performance(portfolioId)
        self.app.db.performances.insert_one(performance)

        transfer_history = self.request_transfer_history(portfolioId, update)
        self.app.db.transfers.inser_one(transfer_history)

        position_history = self.request_position_history(portfolioId, update)
        self.app.db.positions.inser_one(position_history)

        return {portfolioId, details, performance, transfer_history, position_history}

    def tick_positions(self, portfolioId):
        positions = self.request_positions(portfolioId)
        self.app.db.pool.insert_one(positions)

        return {portfolioId, positions}

    # Lifecycle

    def cleanup(self):
        self.gateway.shutdown()


    # def request_rapid_API(self, path, params):
    #     headers = {
    #         "X-RapidAPI-Key": self.RAPID_API_KEY,
    #         "X-RapidAPI-Host": self.RAPID_API_HOST
    #     }
    #     url = self.gen_url(self.RAPID_API_HOST, path)
    #     querystring = str(params)

    #     response = requests.get(url, headers=headers, params=querystring)

    #     print(response.json())

    #     return response
        

    # def request_leaders(self):
    #     params = {
    #         "isTrader" : True,
    #         "isShared": True,
    #         "periodType": "ALL",
    #         "statisticsType": "ROI"
    #     }

    #     response = self.request_rapid_API('v2/searchLeaderboard', params)

    #     return response.json()
        
    
    # def gen_url(self, host, path):
    #     url = 'https://' + host + '/' + path

    #     return url
        
        # Utils
        
    # def cooldown(self):
    #     time.sleep(self.COOLDOWN)