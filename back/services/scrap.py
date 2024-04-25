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

        self.sum_columns = [
            "positionAmount",
            "unrealizedProfit",
            "cumRealized",
            "notionalValue",
            "markPrice",
            "ABSOLUTE_LEVERED_VALUE",
            "ABSOLUTE_UNLEVERED_VALUE"
        ]

        self.average_columns = [
            "entryPrice",
            "markPrice",
            "leverage",
            "breakEvenPrice",
        ]

        self.drop_columns = [
            "id",
            "collateral",
            "isolated",
            "isolatedWallet",
            "adl",
            "askNotional",
            "bidNotional"
        ]

    def cooldown(self):
        # time.sleep(self.COOLDOWN)
        pass

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
                return { "success": False, "message": f"Could not fetch page {params['pageNumber']}/{pages_length} of {endpointType}" }
            
        except Exception as e:
            await self.handle_exception(bot, e, 'fetch_pages', response)

 
    #* UPDATE


    async def leader_detail_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["detail"]["data"]["leadPortfolioId"]

            print(f'[{utils.current_readable_time()}]: Updating Details for {binance_id}')

            detail_response = await self.fetch_data(bot, binance_id, 'detail')
            detail = detail_response["data"]

            detail_update = {
                "detail":  detail
            }

            return detail_update
        
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_detail_update', None)


    async def leader_performance_update(self, bot, leader=None, binance_id:str=None):
        try:
            if leader:
                binance_id = leader["detail"]["data"]["leadPortfolioId"]

            print(f'[{utils.current_readable_time()}]: Updating Performance for {binance_id}')

            performance_response = await self.fetch_data(bot, binance_id, 'performance')
            performance = performance_response["data"]

            performance_update = {
                "performance": performance
            }

            return performance_update
    
        except Exception as e:
            await self.handle_exception(bot, e, 'leader_performance_update', None)
        

    def aggregate_leader_positions(self, group: pd.DataFrame, handle_position_direction=False) -> pd.Series:
        result = {}
        
        for key in self.sum_columns: 
            result[key] = group[key].sum() if key in group.keys() else None
        for key in self.average_columns:
            #! not good
            result[key] = np.average(group[key], weights=group["ABSOLUTE_LEVERED_VALUE"].abs()) if key in group.keys() else None

        if handle_position_direction:
            if len(group) > 1: result["positionSide"] = "BOTH"
            else: result["positionSide"] = group["positionSide"].values[0]

        # result["LEADER_IDS"] = list(set(group["LEADER_ID"]))
        return pd.Series(result)

    async def leader_positions_update(self, bot, leader):
        # try:

            binance_id = leader["detail"]["data"]["leadPortfolioId"]

            positions_response = await self.fetch_data(bot, binance_id, 'positions')
            positions = pd.DataFrame(positions_response["data"])

            if len(positions) > 0:
                positions["ID"] = str(leader["_id"])
                positions = positions.set_index("ID")
                positions = positions.apply(lambda column: column.astype(float) if column.name in self.sum_columns + self.average_columns else column)
                # print("POSITIONS")
                # print(positions)
                # print("")
                # print("POSITIONS")
                # print(positions.dtypes)
                # print("")
                # print(binance_id)
                filtered_positions = positions.loc[(positions["positionAmount"] != 0) & (positions["collateral"] == "USDT")]
                filtered_positions = filtered_positions.drop(columns=self.drop_columns)
                filtered_positions["ABSOLUTE_LEVERED_VALUE"] = filtered_positions["notionalValue"].abs()
                filtered_positions["ABSOLUTE_UNLEVERED_VALUE"] = filtered_positions["ABSOLUTE_LEVERED_VALUE"] / filtered_positions["leverage"]
                # print("FILTERED_POSITIONS")
                # print(filtered_positions)
                # print("")
                grouped_positions = filtered_positions.groupby("symbol").apply(self.aggregate_leader_positions, handle_position_direction=True, include_groups=False).reset_index()
                grouped_positions = grouped_positions.loc[(grouped_positions["positionAmount"] != 0)]
                # print("GROUPED_POSITIONS")
                # print(grouped_positions)
                # print("")
                grouped_positions["ID"] = str(leader["_id"])
                grouped_positions = grouped_positions.rename(columns={key: key + "_SUM" for key in self.sum_columns} | {key: key + "_AVERAGE" for key in self.average_columns}).set_index("ID")
                grouped_positions["LEVERED_POSITION_SHARE"] = grouped_positions["ABSOLUTE_LEVERED_VALUE_SUM"] / grouped_positions["ABSOLUTE_LEVERED_VALUE_SUM"].sum()
                grouped_positions["UNLEVERED_POSITION_SHARE"] = grouped_positions["ABSOLUTE_UNLEVERED_VALUE_SUM"] / grouped_positions["ABSOLUTE_UNLEVERED_VALUE_SUM"].sum()
                # total_balance = leader["account"]["data"]["total_balance"]
                total_balance = float(leader["detail"]["data"]["marginBalance"])
                levered_ratio = grouped_positions["ABSOLUTE_LEVERED_VALUE_SUM"].sum() / total_balance
                unlevered_ratio = grouped_positions["ABSOLUTE_UNLEVERED_VALUE_SUM"].sum() / total_balance

                grouped_positions["LEVERED_RATIO"] = levered_ratio
                grouped_positions["UNLEVERED_RATIO"] = unlevered_ratio
                # print("GROUPED_POSITIONS")
                # print(grouped_positions)
                # print("")
                positions_update = {
                    "account": {
                    "levered_ratio": levered_ratio,
                        "unlevered_ratio": unlevered_ratio,
                    },
                    "positions": filtered_positions.to_dict(),
                    "grouped_positions": grouped_positions.to_dict()
                }

                return positions_update, grouped_positions[["symbol", "positionAmount_SUM", "markPrice_AVERAGE", "LEVERED_POSITION_SHARE", "LEVERED_RATIO", "UNLEVERED_RATIO"]]

            return positions, []
        # except Exception as e:
        #     await self.handle_exception(bot, e, 'leader_positions_update', None)
    

    async def get_leader(self, bot, user, leader_id=None, binance_id:str=None):
        # try:
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
                        "data":{}
                        },
                    "positions":{
                        "data":[]
                        },
                    "grouped_positions":{
                        "data":[]
                        },
                    "mix":{
                        "data":[]
                        },
                    "performance":{
                        "data":{}
                        },
                }
                await self.app.database.update(obj=leader, update=detail, collection='leaders')

            if "updated" not in leader["detail"].keys() or utils.current_time() - leader["detail"]["updated"] > 3600000:
                detail = await self.leader_detail_update(bot, leader=leader)
                await self.app.database.update(obj=leader, update=detail, collection='leaders')
                #! -> remove leader from user list

            if "updated" not in leader["performance"].keys() or utils.current_time() - leader["performance"]["updated"] > 3600000:
                performance = await self.leader_performance_update(bot, leader=leader)
                await self.app.database.update(obj=leader, update=performance, collection='leaders')

            if leader["detail"]["data"]["positionShow"] and leader["detail"]["data"]["status"] == "ACTIVE" and leader["detail"]["data"]["initInvestAsset"] == "USDT":
                positions, grouped_positions = await self.leader_positions_update(bot, leader)

                if len(grouped_positions) > 0:
                    await self.app.database.update(obj=leader, update=positions, collection='leaders')
                
                # print(grouped_positions)
                return leader, grouped_positions

            else:
                #* to be updated correctly
                user["leaders"]["data"]["WEIGHT"].pop(str(leader["_id"]))

                return leader, []

        # except Exception as e:
        #     await self.handle_exception(bot, e, 'get_leader', None)
    #* LIFECYCLE


    async def handle_exception(self, bot, error, source, details):
        trace = traceback.format_exc()

        await self.app.log.create(bot, bot, 'ERROR', f'scrap/{source}', 'SCRAP', f'Error in {source} - {error}', details={"trace": trace, "log": details})

        self.cleanup()
        self.start()

        pass
    
    
    def start(self):
        self.gateway = ApiGateway(self.GATEWAY_HOST, regions=["eu-west-1", "eu-west-2"], access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'), access_key_secret=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        self.gateway.start()
        self.session = requests.Session()
        self.session.mount(self.GATEWAY_HOST, self.gateway)


    def cleanup(self):
        self.gateway.shutdown()



#    async def leader_account_update(self, leader):
#         binance_id = leader["detail"]["data"]["leadPortfolioId"]
        
#         transfer_history_response = await self.fetch_pages(binance_id, 'transfer_history')

#         transfer_history = pd.DataFrame(transfer_history_response)
#         transfer_history["ID"] = str(leader["_id"])
#         transfer_history["INCOMING"] = transfer_history["to"] == 'Lead Trading Account'
#         transfer_history["RELATIVE_VALUE"] = transfer_history.apply(lambda row: row["amount"] if row["INCOMING"] else -row["amount"], axis=1)

#         position_history = await self.fetch_pages(binance_id, 'position_history')
#         position_history = pd.DataFrame(position_history)
#         position_history["ID"] = str(leader["_id"])

#         transfer_balance = transfer_history["RELATIVE_VALUE"].sum()
#         historic_PNL = position_history["closingPnl"].sum()
#         total_balance = transfer_balance + historic_PNL

#         account_update = {
#             "account": {
#                 "transfer_balance": transfer_balance,
#                 "historic_PNL": historic_PNL,
#                 "total_balance": total_balance,
#             },
#         }

#         return account_update





    # async def create_leader(self, leaderId):
    #     try:   
    #         bot = await self.app.db.bot.find_one()
    #         detail_reponse = await self.fetch_data(bot, leaderId, "detail")

    #         if detail_reponse["success"]:
    #             detail_data = detail_reponse["data"]

    #         else:
    #             return { "success": False, "message": "Could not fetch Detail" }
            
    #         if detail_data["positionShow"] == True:
    #             # todo: update leader if fail reasons

    #             if detail_data["status"] != "ACTIVE":
    #                 return { "success": False, "message": "Leader is not Active" }

    #             if detail_data["initInvestAsset"] != "USDT":
    #                 return { "success": False, "message": "Leader is not using USDT" }
                
    #             leader_db = await self.app.db.leaders.find_one({"binanceId": leaderId})

    #             if leader_db:
    #                 leader = leader_db

    #             else:
    #                 leader = {
    #                         "binanceId": leaderId,
    #                         "profileUrl": f'https://www.binance.com/en/copy-trading/lead-details/{leaderId}',
    #                         "userId": detail_data["userId"],
    #                         "nickname": detail_data["nickname"],
    #                         "avatarUrl": detail_data["avatarUrl"],
    #                         "status": detail_data["status"],
    #                         "initInvestAsset": detail_data["initInvestAsset"],
    #                         "positionShow": detail_data["positionShow"],
    #                         "updatedAt": utils.current_time(),
    #                         "historicPNL": 0,
    #                         "transferBalance": 0,
    #                         "totalBalance": 0,
    #                         "liveRatio": 0,
    #                         "positionsValue": 0,
    #                         "positionsNotionalValue": 0,
    #                         "amounts": {},
    #                         "notionalValues": {},
    #                         "values": {},
    #                         "shares": {},
    #                         "leverages": {}
    #                     }
    #                 await self.app.db.leaders.insert_one(leader)

    #             # print(leader_db)

    #             # self.cooldown()
    #             await self.tick_positions(bot, leader)

    #             # self.cooldown()
    #             await self.update_leader_stats(bot, leader)
                
    #             #todo do not replace if nothing changed ?
    #             await self.app.db.leaders.update_one(
    #                 {"_id": leader["_id"]}, 
    #                 {"$set": leader}
    #             )
                
    #             # print(leader)
    #         else:
    #             return { "success": False, "message": "Leader is not sharing Positions" }

    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'create_leader', detail_reponse)


    # async def tick_leader(self, bot, leader):
    #     try:   
    #         detail_reponse = await self.fetch_data(bot, leader["binanceId"], "detail")

    #         if detail_reponse["success"]:
    #             detail_data = detail_reponse["data"]

    #             leader.update({
    #                 "status": detail_data["status"],
    #                 "initInvestAsset": detail_data["initInvestAsset"],
    #                 "positionShow": detail_data["positionShow"],
    #                 "updatedAt": utils.current_time(),
    #             })


    #             await self.app.db.leaders.update_one(
    #                 {"_id": leader["_id"]}, 
    #                 {"$set": leader}
    #             )
            
    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'tick_leader', detail_reponse)


    # async def update_leader_stats(self, bot, leader):
    #     try:
    #         await self.tick_position_history(bot, leader)

    #         # self.cooldown()
    #         await self.tick_transfer_history(bot, leader)
        
    #         total_balance = leader["historicPNL"] + leader["transferBalance"] + leader["positionsValue"]

    #         update = {
    #             "totalBalance": total_balance,
    #             "liveRatio": leader["positionsValue"] / total_balance,
    #             "updatedAt": utils.current_time()
    #         }

    #         leader.update(update)

    #         await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

    #         return update
    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'update_leader_stats', leader)

    
    # async def tick_transfer_history(self, bot, leader):
    #     try:
    #         latest_transfer = await self.app.db.transfer_history.find_one(
    #                 {"leaderId": leader["_id"]},
    #                 sort=[('time', -1)]
    #             )

    #         transfer_history_response = await self.fetch_pages(bot, leader["binanceId"], "transfer_history", reference='time', latest_item=latest_transfer)
    #         # print(transfer_history_response)
    #         # transfers = []

    #         if transfer_history_response["success"]:
    #             transfer_history = transfer_history_response["data"]

    #             for transfer in transfer_history:
    #                 # if "transType" in transfer.keys():
    #                     transfer["leaderId"] = leader["_id"]
    #                     transfer_type = transfer["transType"]

    #                     if transfer_type == "LEAD_INVEST" or transfer_type == "LEAD_DEPOSIT":
    #                         leader["transferBalance"] += float(transfer["amount"])

    #                     elif transfer_type == "LEAD_WITHDRAW":
    #                         leader["transferBalance"] -= float(transfer["amount"])

    #                     else:
    #                         print(f"WARNING! UNKNOWN TRANFER TYPE: {transfer_type}")

    #                     # transfers.append(transfer)

    #             if len(transfer_history) > 0:
    #                 await self.app.db.transfer_history.insert_many(transfer_history)

    #         return transfer_history_response
        
    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'tick_transfer_history', transfer_history_response)


    # async def tick_position_history(self, bot, leader):
    #     try:
    #         latest_position = await self.app.db.position_history.find_one(
    #             {"leaderId": leader["_id"]},
    #             sort=[('updateTime', -1)]
    #         )
            
    #         position_history_response = await self.fetch_pages(bot, leader["binanceId"], "position_history", reference='updateTime', latest_item=latest_position)

    #         if position_history_response["success"]:
    #             new_position_history = position_history_response["data"]
    #             partially_closed_positions = await self.app.db.position_history.distinct('id', {'status': 'Partially Closed'})
    #             new_positions = []
    #             # print(partially_closed_positions)
    #             for position in new_position_history:
    #                 position["leaderId"] = leader["_id"]

    #                 if position["id"] in partially_closed_positions:
    #                     partially_closed_position = await self.app.db.position_history.find_one({"leaderId": leader["_id"], "id": position["id"]})
    #                     leader['historicPNL'] -= float(partially_closed_position["closingPnl"])

    #                     await self.app.db.position_history.replace_one({"leaderId": leader["_id"], "id": position["id"]}, position)
    #                 else:
    #                     leader['historicPNL'] += float(position["closingPnl"])
    #                     new_positions.append(position)

    #             if len(new_positions) > 0:
    #                 await self.app.db.position_history.insert_many(new_positions)
                
    #         return position_history_response
        
    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'tick_position_history', position_history_response)


    # async def tick_positions(self, bot, leader):
    #     try:
    #         binanceId = leader["binanceId"]
    #         fetch_data_response = await self.fetch_data(bot, binanceId, "positions")

    #         if fetch_data_response["success"]:
    #             positions_data = fetch_data_response["data"]
    #             latest_amounts = leader["amounts"]
    #             positions_notional_value = 0
    #             positions_value = 0
    #             positions = []
    #             amounts, values, notional_values, shares, leverages = {}, {}, {}, {}, {}

    #             for position in positions_data:
    #                 position_amount = float(position["positionAmount"])
    #                 symbol, _ = await self.app.binance.get_asset_precision(bot, position["symbol"])

    #                 if symbol and position_amount != 0:
    #                     position["leaderId"] = leader["_id"]
    #                     leverage = position["leverage"]
    #                     notional_value = float(position["notionalValue"])
    #                     position_value = abs(notional_value / leverage)

    #                     if symbol not in amounts: 
    #                         amounts[symbol] = 0
    #                         notional_values[symbol] = 0
    #                         values[symbol] = 0

    #                     amounts[symbol] += position_amount
    #                     notional_values[symbol] += notional_value
    #                     values[symbol] += position_value
    #                     leverages[symbol] = leverage

    #                     positions_notional_value += abs(notional_value)
    #                     positions_value += position_value
    #                     positions.append(position)
    #             # print(values)
    #             if amounts != latest_amounts:
    #                 current_set, last_set = set(amounts.items()), set(latest_amounts.items())
    #                 current_difference, last_difference = current_set.difference(last_set), last_set.difference(current_set)

    #                 for bag in last_difference:
    #                     symbol, amount = bag

    #                     if amount != 0:
    #                         if symbol not in amounts:
    #                             # print(f'{bag} CLOSED POSITION')
    #                             await self.app.db.positions.delete_one({"leaderId": leader["_id"], "symbol": symbol})

    #                 for bag in current_difference:
    #                     symbol, amount = bag

    #                     if amount != 0:
    #                         symbol_positions = [position for position in positions if position.get('symbol') == symbol]

    #                         if symbol in latest_amounts:
    #                             # print(f'{bag} CHANGED POSITION')
    #                             for symbol_position in symbol_positions:
    #                                 await self.app.db.positions.replace_one({"leaderId": leader["_id"], "id": symbol_position["id"]}, symbol_position)
    #                         else:
    #                             # print(f'{bag} NEW POSITION')
    #                             for symbol_position in symbol_positions:
    #                                 await self.app.db.positions.insert_one(symbol_position)

    #             for symbol, value in values.items():
    #                 shares[symbol] = value / positions_value

    #             update = {
    #                 "positionsValue": positions_value,
    #                 "positionsNotionalValue": positions_notional_value,
    #                 "amounts": amounts,
    #                 "notionalValues": notional_values,
    #                 "shares": shares,
    #                 "values": values,
    #                 "leverages": leverages,
    #                 "updatedAt": utils.current_time(),
    #                 }
    #             # print(update)
    #             leader.update(update)

    #             await self.app.db.leaders.update_one({"_id": leader["_id"]}, {"$set": update})

    #             # if len(unknown_symbols) > 0:
    #             #     self.app.db.bot.update_one({}, {"$set": {"symbols": bot["symbols"]}})

    #         return fetch_data_response
        
    #     except Exception as e:
    #         await self.handle_exception(bot, e, 'tick_positions', fetch_data_response)
