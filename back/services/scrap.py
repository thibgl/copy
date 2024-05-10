import os
import requests
from requests_ip_rotator import ApiGateway, EXTRA_REGIONS
from fake_useragent import UserAgent
from lib import utils
import traceback
import time
from tqdm import tqdm
import pandas as pd
import numpy as np
from bson.objectid import ObjectId

endpoints = {
    "leaders": {
        "path": "friendly/future/copy-trade/home-page/query-list",
        "type": "paginated",
        "params": {
            "dataType": "ROI",
            "favoriteOnly": False,
            "hideFull": False,
            "nickname": "",
            "order": "DESC",
            "pageNumber": 1,
            "pageSize": 18,
            "portfolioType": "PUBLIC",
            "timeRange": "90D"
            # "userAsset": 17880.26883363
        }
    },
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
        self.GATEWAY_HOST = 'https://www.binance.com'
        self.API_PATH = '/'.join([self.GATEWAY_HOST, 'bapi/futures/v1'])
        self.COOLDOWN = 0.2

        self.app = app
        self.gateway = None
        self.session = None
        self.user_agent = UserAgent()

        self.start()


    def gen_headers(self):
        headers = {'User-Agent':str(self.user_agent.random)}
        # print(headers)

        return headers
    

    #* FETCH
    

    async def fetch_data(self, bot, leaderId, endpointType):
        response = None
        try:
            endpoint = endpoints[endpointType]
            params = endpoint["params"]
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
            # print(response.json())
            return response.json()
        
        except Exception as e:
            await self.handle_exception(bot, e, 'fetch_data', response)
            self.cleanup()
            self.start()
            return {"code": "-1"}


    async def fetch_pages(self, bot, endpointType, params=None, leaderId=None, results_limit=0, latest_item=None, reference=None, progress_bar=None):
        try:
            total_n_results = 0
            if params is None:
                params = endpoints[endpointType]["params"]

            while True:
                response = await self.fetch_data(bot, leaderId, endpointType)

                if response["code"] == '000000':
                    response_data = response["data"]
                    response_list = response_data["list"]
                    total_n_results += len(response_list)

                    if latest_item and reference:
                        response_list = sorted(response_list, key=lambda x: x[reference], reverse=True)
                        filtered_list = [item for item in response_list if item[reference] > latest_item[reference]]

                        if filtered_list:
                            yield filtered_list
                            params["pageNumber"] += 1
                        else:
                            # No more items to fetch that are newer than the latest item
                            break
                    else:
                        if progress_bar is None:
                            progress_bar = tqdm(total=results_limit if results_limit else response_data["total"])

                        progress_bar.update(len(response_list))
                        yield response_list

                        # Check if more pages should be fetched
                        if params["pageNumber"] * params["pageSize"] >= response_data["total"] or (total_n_results >= results_limit):
                            break
                        params["pageNumber"] += 1
                else:
                    # Handle failed response code
                    yield { "success": False, "message": f"Could not fetch page {params['pageNumber']} of {endpointType}", "data": {} }
                    break

        except Exception as e:
            await self.handle_exception(bot, e, 'fetch_pages', response)
            yield { "success": False, "message": f"Exception occurred: {str(e)}", "data": {} }

 
    #* UPDATE


    async def leader_detail_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["binanceId"]

            print(f'[{utils.current_readable_time()}]: Updating Details for {binance_id}')

            detail_response = await self.fetch_data(bot, binance_id, 'detail')

            if detail_response["code"] == '000000':
                detail = detail_response["data"]
                detail_update = {
                    "detail":  detail
                }

                return detail_update

            elif detail_response["code"] == '11012028': # closed portfolio
                return None
            
            else:
                await self.handle_exception(bot, 'e', f'leader_detail_update - NO FETCH for {binance_id}', None)
                return {"detail": leader["detail"]["data"]}
            
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_detail_update', None)


    async def leader_performance_update(self, bot, leader):
        try:
            binance_id = leader["binanceId"]

            print(f'[{utils.current_readable_time()}]: Updating Performance for {binance_id}')

            performance_response = await self.fetch_data(bot, binance_id, 'performance')

            if performance_response and 'data' in performance_response.keys():
                performance = performance_response["data"]

                performance_update = {
                    "performance": performance
                }

                return performance_update
    
            else:
                await self.handle_exception(bot, 'e', f'leader_performance_update - NO FETCH for {binance_id}', None)
                return {"performance": leader["performance"]["data"]}
        
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_performance_update', None)
        

    async def leader_chart_update(self, bot, leader):
        try:
            binance_id = leader["binanceId"]

            print(f'[{utils.current_readable_time()}]: Updating Chart for {binance_id}')

            chart_response = await self.fetch_data(bot, binance_id, 'chart')

            if chart_response and 'data' in chart_response.keys():

                chart = chart_response["data"]

                chart_update = {
                    "chart": chart
                }

                return chart_update
            
            else:
                await self.handle_exception(bot, 'e', f'leader_chart_update - NO FETCH for {binance_id}', None)
                return {"chart": leader["chart"]["data"]}
    
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_chart_update', None)


    async def leader_positions_update(self, bot, leader, lifecycle):
        try:
            binance_id = leader["binanceId"]
            positions_response = await self.fetch_data(bot, binance_id, 'positions')
            
            if positions_response["code"] == '000000':
                positions = pd.DataFrame(positions_response["data"])

                positions["ID"] = binance_id
                positions = positions.set_index("ID")
                positions = positions.apply(lambda column: column.astype(float) if column.name in ["markPrice", "positionAmount", "notionalValue", "leverage", "unrealizedProfit"] else column)
        
                filtered_positions = positions.copy().loc[(positions["positionAmount"] != 0) & (positions["collateral"] == "USDT")]

                if len(filtered_positions) > 0:
                    filtered_positions["UNLEVERED_VALUE"] = filtered_positions["notionalValue"] / filtered_positions["leverage"]
                    filtered_positions["POSITION_SHARE"] = filtered_positions["notionalValue"].abs() / filtered_positions["notionalValue"].abs().sum()
                    filtered_positions["leverage_WEIGHTED"] = filtered_positions["leverage"] * filtered_positions["POSITION_SHARE"]
        
                    grouped_positions = filtered_positions.groupby("symbol").agg({
                        "markPrice": 'mean',
                        "positionAmount": 'sum',
                        "notionalValue": 'sum',
                        "UNLEVERED_VALUE": 'sum',
                        "unrealizedProfit": 'sum',
                        "POSITION_SHARE": 'sum',
                        "leverage_WEIGHTED": 'mean'
                        }).reset_index()

                    grouped_positions = grouped_positions.loc[(grouped_positions["positionAmount"] != 0)]
                    grouped_positions["ID"] = str(binance_id)
                    grouped_positions = grouped_positions.set_index("ID")

                    total_levered_value = grouped_positions["notionalValue"].abs().sum()
                    total_unlevered_value = grouped_positions["UNLEVERED_VALUE"].abs().sum()

                    total_balance = float(leader["detail"]["data"]["marginBalance"])
                    levered_ratio = total_levered_value / total_balance
                    unlevered_ratio = total_unlevered_value / total_balance
                    
                    average_leverage = levered_ratio / unlevered_ratio
                    scaled_unlevered_ratio = 4 / ((1 + unlevered_ratio) ** 2) * unlevered_ratio

                    if "ticks" in leader["account"]["data"].keys():
                        ticks = leader["account"]["data"]["ticks"] + 1
                    else:
                        ticks = 1

                    if "average_levered_ratio" not in leader["account"]["data"].keys():
                        average_levered_ratio = levered_ratio
                    else:
                        average_levered_ratio = leader["account"]["data"]["average_levered_ratio"] + (levered_ratio - leader["account"]["data"]["average_levered_ratio"]) / ticks

                    if "average_unlevered_ratio" not in leader["account"]["data"].keys():
                        average_unlevered_ratio = unlevered_ratio
                    else:
                        average_unlevered_ratio = leader["account"]["data"]["average_unlevered_ratio"] + (unlevered_ratio - leader["account"]["data"]["average_unlevered_ratio"]) / ticks

                    grouped_positions["PROFIT"] = -grouped_positions["unrealizedProfit"] / (grouped_positions["positionAmount"] * grouped_positions["markPrice"]) * 1000
                    grouped_positions["TICKS"] = ticks
                    grouped_positions["ROI"] = leader["performance"]["data"]["roi"]
                    # print(leader["performance"]["data"])
                    grouped_positions["SHARP"] = float(leader["performance"]["data"]["sharpRatio"]) if leader["performance"]["data"]["sharpRatio"] else 0
                    grouped_positions["AVERAGE_LEVERAGE"] = average_leverage
                    grouped_positions["INVESTED_RATIO"] = unlevered_ratio

                    positions_update = {
                        "account": {
                            "ticks": ticks,
                            "levered_ratio": levered_ratio,
                            "unlevered_ratio": unlevered_ratio,
                            "average_levered_ratio": average_levered_ratio,
                            "average_unlevered_ratio": average_unlevered_ratio,
                        },
                        "positions": filtered_positions.to_dict(),
                        "grouped_positions": grouped_positions.to_dict(),
                    }
# , "SHARP"
                    return positions_update, grouped_positions[["symbol", "positionAmount", "markPrice", "PROFIT", "SHARP", "ROI", "AVERAGE_LEVERAGE", "INVESTED_RATIO", "POSITION_SHARE"]]
                
                else:
                    return {}, []
                    
            else:
                await self.handle_exception(bot, 'e', f'leader_positions_update - NO FETCH for {binance_id}', None)
                lifecycle["tick_boost"], lifecycle["reset_rotate"] = True, True
                if leader["grouped_positions"]["data"]:
                    return {}, pd.DataFrame(leader["grouped_positions"]["data"])
                else:
                    return {}, []
            
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_positions_update', None)


    async def get_leader(self, bot, binance_id):
        try:
            leader = await self.app.db.leaders.find_one({"binanceId": binance_id})

            if not leader:
                update = {}
                detail_update = await self.leader_detail_update(bot, binance_id=binance_id)
                
                if detail_update:
                    update.update(detail_update)
                    detail = detail_update["detail"]

                    leader = {
                        "binanceId": detail["leadPortfolioId"],
                        "detail":{
                            "data":{}
                        },
                        "account":{
                            "data":{
                                "levered_ratio": 0,
                                "unlevered_ratio": 0
                            }
                        },
                        "positions":{
                            "data":{}
                        },
                        "grouped_positions":{
                            "data":{}
                        },
                        "mix":{
                            "data":[]
                        },
                        "performance":{
                            "data":{}
                        },
                        "chart":{
                            "data":[]
                        },
                    }

                    if detail["positionShow"] and detail["status"] == "ACTIVE" and detail["initInvestAsset"] == "USDT":
                        status = 'ACTIVE'
                        chart_update = await self.leader_chart_update(bot, leader=leader)
                        performance_update = await self.leader_performance_update(bot, leader=leader)
                        update.update(chart_update | performance_update)
                    else:
                        status = 'INACTIVE'

                    update["status"] = status
                    await self.app.database.update(obj=leader, update=update, collection='leaders')
                else:
                    return None
                
            return leader

        except Exception as e:
            await self.handle_exception(bot, e, 'get_leader', None)

    async def update_leader(self, bot, leader):
        if utils.current_time() - leader["detail"]["updated"] > 3600000:
            update = {}
            detail_update = await self.leader_detail_update(bot, leader=leader)

            if detail_update:
                update.update(detail_update)
                detail = detail_update["detail"]

                if detail["positionShow"] and detail["status"] == "ACTIVE" and detail["initInvestAsset"] == "USDT":
                    status = 'ACTIVE'
                else:
                    status = 'INACTIVE'

                if utils.current_time() - leader["chart"]["updated"] > 3600000 * 3:
                    chart_update = await self.leader_chart_update(bot, leader=leader)
                    update.update(chart_update)

                if utils.current_time() - leader["performance"]["updated"] > 3600000 * 3:
                    performance_update = await self.leader_performance_update(bot, leader=leader)
                    update.update(performance_update)
            else:
                status = 'CLOSED'

            update["status"] = status
            await self.app.database.update(obj=leader, update=update, collection='leaders')
            
            # if status == 'CLOSED':
            #     return None
                    
    async def update_leaders(self, bot, user):
        try:
            active_leaders = user["leaders"]["data"]["WEIGHT"].keys()
            for binance_id in active_leaders:
                leader = await self.app.db.leaders.find_one({"binanceId": binance_id})
                await self.update_leader(bot, leader)

            limit = 20 - len(active_leaders)
            unactive_leaders = self.app.db.leaders.find({'status': 'ACTIVE', 'updated': {'$lt': utils.current_time() - 3600000 * 12}}).limit(limit)
            async for leader in unactive_leaders:
                await self.update_leader(bot, leader)

        except Exception as e:
            await self.handle_exception(bot, e, 'update_leaders', None)

    #* LIFECYCLE


    async def handle_exception(self, bot, error, source, details):
        trace = traceback.format_exc()
        print(trace)

        await self.app.log.create(bot, bot, 'ERROR', f'scrap/{source}', 'SCRAP', f'Error in {source} - {error}', details={"trace": trace, "log": details})
    
    def start(self):
        self.gateway = ApiGateway(self.GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)


    def cleanup(self):
        self.gateway.shutdown()
