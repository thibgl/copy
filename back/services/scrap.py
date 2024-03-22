import os
import requests
import time
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS

http_proxy  = "http://91.121.49.245:7497"
https_proxy = "https://91.121.49.245:7497"
ftp_proxy   = "ftp://91.121.49.245:7497"



class Scrap:
    def __init__(self, app):
        self.app = app
        self.RAPID_API_KEY = os.environ.get('RAPID_API_KEY')
        self.RAPID_API_HOST = os.environ.get('RAPID_API_HOST')
        self.PUBLIC_API_HOST = 'www.binance.com/bapi/futures/v1/public/future/copy-trade'
        self.COOLDOWN = 0.2
        self.GATEWAY_HOST = os.environ.get('API_GATEWAY_HOST')
        self.gateway = ApiGateway(self.GATEWAY_HOST, access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)
        self.proxies = { 
                    "http"  : http_proxy, 
                    "https" : https_proxy, 
                    "ftp"   : ftp_proxy
                    }
                    
    # Utils
        
    def cooldown(self):
        time.sleep(self.COOLDOWN)

    def gen_url(self, host, path):
        url = 'https://' + host + '/' + path

        return url
    
    def request_rapid_API(self, path, params):
        headers = {
            "X-RapidAPI-Key": self.RAPID_API_KEY,
            "X-RapidAPI-Host": self.RAPID_API_HOST
        }
        url = self.gen_url(self.RAPID_API_HOST, path)
        querystring = str(params)

        response = requests.get(url, headers=headers, params=querystring)

        print(response.json())

        return response

    # Requests

    def request_leaders(self):
        params = {
            "isTrader" : True,
            "isShared": True,
            "periodType": "ALL",
            "statisticsType": "ROI"
        }

        response = self.request_rapid_API('v2/searchLeaderboard', params)

        return response.json()
    
    def request_basic_data(self, path_string, portfolioId):
        path = {path_string %(portfolioId)}
        url = self.gen_url(self.PUBLIC_API_HOST, path)

        response = requests.get(url) # , proxies=self.proxies

        return response.json().data
    
    def request_advanced_data(self, path, params, all = False):
        url = self.gen_url(self.PUBLIC_API_HOST, path)

        response = requests.post(url, params)

        return response.json().data

    def request_chart_data(self, portfolioId):
        path_string = '/lead-portfolio/chart-data?dataType=ROI&portfolioId=%s&timeRange=90D'
        data = self.request_base_data(path_string, portfolioId)

        return data
    
    def request_details(self, portfolioId):
        path_string = 'lead-portfolio/detail?portfolioId=%s&timeRange=90D'
        data = self.request_base_data(path_string, portfolioId)

        return data
    

    def request_performance(self, portfolioId):
        path_string = 'lead-portfolio/performance?portfolioId=%s&timeRange=90D'
        data = self.request_base_data(path_string, portfolioId)

        return data
    
        
    def request_positions(self, portfolioId):
        path = f'/lead-data/positions?portfolioId={portfolioId}'
        response = self.session.get(self.GATEWAY_HOST + path)
        print(response.json())

        # return data
    
    def request_position_history(self, portfolioId, update):
        path = 'lead-portfolio/position-history'
        params = {
            "pageNumber": 1,
            "portfolioId": portfolioId
        }
        data = self.request_advanced_data(path, portfolioId, params, all)

        return data
    
    def request_transfer_history(self, portfolioId, update):
        path = 'lead-portfolio/transfer-history'
        params = {
            "pageNumber": 1,
            "portfolioId": portfolioId
        }
        data = self.request_advanced_data(path, portfolioId, params, all)

        return data

    # DB Injections

    def tick_leader(self, portfolioUrl, update=True):
        portfolioId = self.extractPortfolioId(portfolioUrl)

        details = self.request_details(portfolioId)
        self.app.db.leaders.insert_one(details)
        self.cooldown()

        performance = self.request_performance(portfolioId)
        self.app.db.performances.insert_one(performance)
        self.cooldown()

        transfer_history = self.request_transfer_history(portfolioId, update)
        self.app.db.transfers.inser_one(transfer_history)
        self.cooldown()

        position_history = self.request_position_history(portfolioId, update)
        self.app.db.positions.inser_one(position_history)
        self.cooldown()

        return {portfolioId, details, performance, transfer_history, position_history}

    def tick_positions(self, portfolioId):
        positions = self.request_positions(portfolioId)
        self.app.db.pool.insert_one(positions)

        return {portfolioId, positions}
