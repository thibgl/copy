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


    async def fetch_pages(self, bot, endpointType, params=None, leaderId=None, result=None, results_limit=0, latest_item=None, reference=None, progress_bar=None):
        response = None
        try:
            if result is None:
                result = []
            if params is None:
                params = endpoints[endpointType]["params"]

            response = await self.fetch_data(bot, leaderId, endpointType)

            if response["code"] == '000000':
                response_data = response["data"]
                response_list = response_data["list"]

                if latest_item and reference:
                    response_list = sorted(response_list, key=lambda x: x[reference], reverse=True)
                    item_index = 0

                    for item in response_list:
                        if item[reference] > latest_item[reference]:
                            result.append(item)
                            item_index += 1

                            if item_index == 10:
                                params["pageNumber"] += 1
                                return await self.fetch_pages(bot, endpointType, params, leaderId, result, latest_item=latest_item, reference=reference, progress_bar=progress_bar)
                        else:
                            # print({ "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result })
                            return { "success": True, "reason": "partial", "message": f"Fetched pages {endpointType} - finished by update", "data": result }
                else:
                    result += response_list
                    total_n_results = response_data["total"]
                    pages_length = total_n_results // 10

                    if progress_bar is None:
                        await self.app.log.create(bot, bot, 'INFO', 'scrap/fetch_pages', 'SCRAP/CREATE',f'Scraping {endpointType} for {leaderId}')
                        progress_bar = tqdm(total=results_limit if results_limit else total_n_results)

                    progress_bar.update(len(response_list))
                    # If remainder, add another page
                    if total_n_results % 10:
                        pages_length += 1

                    if params["pageNumber"] <= pages_length and total_n_results < results_limit:
                        params["pageNumber"] +=1

                        return await self.fetch_pages(bot, endpointType, params, leaderId, result, progress_bar=progress_bar)
                    else:
                        return { "success": True, "reason": "full", "message": f"Fetched all pages of {endpointType}", "data": result }
            
            else:
                return { "success": False, "message": f"Could not fetch page {params['pageNumber']}/{pages_length} of {endpointType}", "data": {} }
            
        except Exception as e:
            await self.handle_exception(bot, e, 'fetch_pages', response)

 
    #* UPDATE


    async def leader_detail_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["detail"]["data"]["leadPortfolioId"]

            print(f'[{utils.current_readable_time()}]: Updating Details for {binance_id}')

            detail_response = await self.fetch_data(bot, binance_id, 'detail')
            
            if detail_response and 'data' in detail_response.keys():

                detail = detail_response["data"]

                detail_update = {
                    "detail":  detail
                }

                return detail_update
        
            else:
                await self.handle_exception(bot, 'e', f'leader_detail_update - NO FETCH for {binance_id}', None)
                return {"detail": leader["detail"]["data"]}
            
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_detail_update', None)


    async def leader_performance_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["detail"]["data"]["leadPortfolioId"]

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
        

    async def leader_chart_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["detail"]["data"]["leadPortfolioId"]

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
            binance_id = leader["detail"]["data"]["leadPortfolioId"]
            positions_response = await self.fetch_data(bot, binance_id, 'positions')

            if positions_response and 'data' in positions_response.keys():
                positions = pd.DataFrame(positions_response["data"])

                positions["ID"] = binance_id
                positions = positions.set_index("ID")
                positions = positions.apply(lambda column: column.astype(float) if column.name in ["markPrice", "positionAmount", "notionalValue", "leverage"] else column)
        
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

                    grouped_positions["TICKS"] = ticks
                    grouped_positions["PERFORMANCE"] = leader["performance"]["data"]["roi"]
                    grouped_positions["AVERAGE_LEVERAGE"] = average_leverage
                    grouped_positions['INVESTED_RATIO'] = levered_ratio if levered_ratio <= 1 else unlevered_ratio

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

                    return positions_update, grouped_positions[["symbol", "positionAmount", "markPrice", "PERFORMANCE", "AVERAGE_LEVERAGE", "INVESTED_RATIO", "POSITION_SHARE"]]
                
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
    

    async def get_leader(self, bot, user, lifecycle, leader_id=None, binance_id:str=None):
        try:
            if leader_id:
                leader = await self.app.db.leaders.find_one({"_id": ObjectId(leader_id)})
            
            if binance_id:
                leader = await self.app.db.leaders.find_one({"binanceId": binance_id})

            if not leader:
                detail = await self.leader_detail_update(bot, binance_id=binance_id)
                leader = {
                    "binanceId": detail["detail"]["leadPortfolioId"],
                    "detail":{
                        "data":{}
                    },
                    "account":{
                        "data":{
                            "levered_ratio": 0,
                            "unleverd_ratio": 0
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
                await self.app.database.update(obj=leader, update=detail, collection='leaders')

            if leader["detail"]["data"]["positionShow"] and leader["detail"]["data"]["status"] == "ACTIVE" and leader["detail"]["data"]["initInvestAsset"] == "USDT":            
                positions, grouped_positions = await self.leader_positions_update(bot, leader, lifecycle)

                if len(grouped_positions) > 0:
                    await self.app.database.update(obj=leader, update=positions, collection='leaders')

                # print(grouped_positions)
                return leader, grouped_positions

            else:
                #* to be updated correctly
                user["leaders"]["data"]["WEIGHT"].pop(str(leader["_id"]))

                return leader, []

        except Exception as e:
            await self.handle_exception(bot, e, 'get_leader', None)


    async def update_leaders(self, bot, roster):
        for binance_id in roster.index.values:
            leader = await self.app.db.leaders.find_one({"binanceId": binance_id})
            update = {}

            if utils.current_time() - leader["detail"]["updated"] > 3600000 * 3:
                detail = await self.leader_detail_update(bot, leader=leader)
                update.update(detail)

            if utils.current_time() - leader["chart"]["updated"] > 3600000 * 3:
                chart = await self.leader_chart_update(bot, leader=leader)
                update.update(chart)

            if utils.current_time() - leader["performance"]["updated"] > 3600000:
                performance = await self.leader_performance_update(bot, leader=leader)
                update.update(performance)

            await self.app.database.update(obj=leader, update=update, collection='leaders')


    #* LIFECYCLE


    async def handle_exception(self, bot, error, source, details):
        trace = traceback.format_exc()

        await self.app.log.create(bot, bot, 'ERROR', f'scrap/{source}', 'SCRAP', f'Error in {source} - {error}', details={"trace": trace, "log": details})

        # self.cleanup()
        # self.start()

        # pass
    
    
    def start(self):
        self.gateway = ApiGateway(self.GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)


    def cleanup(self):
        self.gateway.shutdown()
