import os
from binance.spot import Spot
from urllib.parse import urlencode
import traceback
from lib import utils
import pandas as pd
import numpy as np
import math
from decimal import Decimal, ROUND_DOWN
import uuid

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)

class Binance:
    def __init__(self, app):
        self.BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY")
        self.BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY")

        self.app = app
        self.client = Spot(api_key=self.BINANCE_API_KEY, api_secret=self.BINANCE_SECRET_KEY, base_url='https://api1.binance.com')

    async def get_precision(self, bot, user, symbol):
        try:
            symbol_precisions = pd.DataFrame(bot["precisions"]["data"])
            
            if symbol in symbol_precisions.index:
                return symbol, symbol_precisions.loc[symbol]
            
            else:
                precision_response = self.client.exchange_info(symbol=symbol)
                details = precision_response['symbols'][0]

                for symbol_filter in details["filters"]:
                    if symbol_filter["filterType"] == "LOT_SIZE":
                        step_size = symbol_filter["stepSize"]
                        min_quantity = float(symbol_filter["minQty"])
                    if symbol_filter["filterType"] == "NOTIONAL":
                        min_notional = float(symbol_filter['minNotional'])

                precision = [step_size, min_quantity, min_notional]
                symbol_precisions.loc[symbol] = precision

                precisions_update = {
                    "precisions": symbol_precisions.to_dict()
                }
                await self.app.database.update(obj=bot, update=precisions_update, collection='bot')

                return symbol, symbol_precisions.loc[symbol]   
        except Exception as error:
            if error.args[1] == -1121:
                if "ignored_symbols" in user["account"]["data"].keys():
                    ignored_symbols = pd.DataFrame(user["account"]["data"]["ignored_symbols"])
                else:
                    ignored_symbols = pd.DataFrame(columns=["symbol", "time"]).set_index("symbol")
                ignored_symbols.loc[symbol] = utils.current_time()
                user_update = {
                    "account": {
                        "ignored_symbols": ignored_symbols.to_dict()
                    }
                }
                await self.app.database.update(user, user_update, 'users')

                return symbol, pd.Series([])
            else:
                await self.handle_exception(bot, bot, error, 'get_precision', symbol)

    async def get_precisions(self, bot, user, dataframe):
        precisions = pd.DataFrame(columns=["stepSize", "minQty", "minNotional"])

        for symbol in dataframe["final_symbol"].unique():
            symbol, precision = await self.get_precision(bot, user, symbol)

            if not precision.empty:
                precisions.loc[symbol] = precision
            else:
                dataframe = dataframe[dataframe['final_symbol'] != symbol]

        dataframe = dataframe.merge(precisions, left_on="final_symbol", right_index=True, how='left')

        return dataframe

    def get_final_symbol(self, symbol):
        if symbol.startswith('1000') and symbol not in ["1000SATSUSDT"]:
            return pd.Series([symbol[4:], True])
        elif symbol in ["LUNA2USDT"]:
            return pd.Series([symbol.replace('2', ''), False])
        else:
            return pd.Series([symbol, False])
    
    async def get_prices(self, bot, dataframe, existing_price_column=None):
        if existing_price_column:
            dataframe["SYMBOL_PRICE"] = dataframe.apply(lambda row: row[existing_price_column] if pd.notna(row[existing_price_column]) else float(self.app.binance.client.ticker_price(row["symbol"])["price"]), axis=1)
        else:
            dataframe["SYMBOL_PRICE"] = dataframe["SYMBOL_PRICE"].apply(lambda symbol: float(self.app.binance.client.ticker_price(symbol)["price"]))

        dataframe["CURRENT_VALUE"] = dataframe["netAsset"] * dataframe["SYMBOL_PRICE"]

        return dataframe

    def truncate_amount(self, amount, stepSize):
        # print(amount, stepSize)
        # if amount and stepSize:
        #     decimals = stepSize.split('1')[0].count('0')

            # multiplier = 10 ** decimals if decimals > 0 else 1
            # final_amount = math.floor(abs(amount) * multiplier) / multiplier
            # return final_amount if amount >= 0 else -final_amount

            # final_amount = round(amount, decimals)
            # return final_amount

        amount = Decimal(amount)
        decimals = Decimal(stepSize)
        truncated = (amount // decimals) * decimals
        final_amount = float(truncated.quantize(decimals, rounding=ROUND_DOWN))
        # print(final_amount)
        return final_amount

    def validate_amounts(self, dataframe, amount_column, value_column):
        truncated_amount_column = amount_column + "_TRUNCATED"
        dataframe[truncated_amount_column] = dataframe.apply(lambda row: self.truncate_amount(row[amount_column], row["stepSize"]), axis=1)
        dataframe[amount_column + "_PASS"] = (dataframe[value_column].abs() > dataframe["minNotional"] * 1.05) & (dataframe[truncated_amount_column].abs() > dataframe["minQty"])

        return dataframe

    async def user_account_update(self, bot, user, new_positions, user_leaders, mix_diff, dropped_leaders, lifecycle):
        weigth = 10
        try:
            user_leaders = user_leaders.merge(new_positions[['AVERAGE_LEVERAGE']], left_index=True, right_index=True, how='left').groupby(level=0).first()
            # leader_entries = new_positions.groupby("ID").agg({"NOTIONAL_BALANCE": 'first'})
            leader_entries = pd.DataFrame(user["entries"]["data"])
            leader_entries = leader_entries.loc["LAST_ROI" != None]
            margin_account_data = self.client.margin_account()

            assetBTC = float(margin_account_data["totalNetAssetOfBtc"])
            valueUSDT = float(self.client.ticker_price("BTCUSDT")["price"]) * assetBTC
            account_data = {
                    "value_BTC": assetBTC,
                    "value_USDT": valueUSDT,
                    "collateral_margin_level": float(margin_account_data["collateralMarginLevel"]),
                    "collateral_value_USDT": float(margin_account_data["totalCollateralValueInUSDT"]),
            }

            user_positions = pd.DataFrame(margin_account_data["userAssets"])
            for column in user_positions.columns:
                if column != 'asset':
                    user_positions[column] = user_positions[column].astype(float)

            positions_excess = user_positions.copy()[(user_positions["borrowed"] != 0) & (user_positions["borrowed"] > user_positions["netAsset"].abs())].set_index('asset')

            user_positions = user_positions.loc[(user_positions["netAsset"] != 0)]
            user_positions["symbol"] = user_positions["asset"] + 'USDT'
            
            pool = user_positions[['asset', 'symbol', 'netAsset', 'borrowed', 'free', 'interest']]
            live_pool = pool.copy().loc[pool["asset"] != 'USDT']

            ignored_symbols = pd.DataFrame(user["account"]["data"]["ignored_symbols"])
            
            new_positions = new_positions.copy().loc[new_positions["symbol"] != "EMPTY"]
            if len(new_positions) > 0:
                new_positions = new_positions.merge(leader_entries.add_prefix("previous_"), left_index=True, right_index=True, how='left')
                new_positions["LAST_ROI"] = new_positions["NOTIONAL_BALANCE"] / new_positions["previous_NOTIONAL_BALANCE"]
                print(new_positions.copy().groupby('ID').agg({
                    'LAST_ROI': 'first',
                    # 'PROFIT': 'mean',
                    # 'symbol': 'unique'
                }))
                drifters = new_positions.copy().loc[new_positions["LAST_ROI"] < 0.8]
                if len(drifters) > 0:
                    drifters_ids = drifters.index.unique()

                    for drifter_id in drifters_ids:
                        if drifter_id not in dropped_leaders:
                            dropped_leaders.append(drifter_id)
                            await self.app.log.create(bot, user, 'INFO', 'user_account_update', 'MANAGE', f'Removed Drifter: {drifter_id}', details=str(drifters.to_dict()))
                            lifecycle["reset_mix"] = True


                new_positions = new_positions.loc[(new_positions["LAST_ROI"] >= 0.8) | (new_positions["LAST_ROI"].isna())]  
                new_positions[["final_symbol", "thousand"]] = new_positions["symbol"].apply(lambda symbol: self.get_final_symbol(symbol))
                new_positions.loc[new_positions["thousand"], "markPrice"] /= 1000
                # print(new_positions)
                live_pool = live_pool.merge(new_positions.reset_index().add_prefix("leader_"), left_on="symbol", right_on="leader_final_symbol", how='outer')
                live_pool["final_symbol"] = live_pool.apply(lambda row: pd.Series(row["leader_final_symbol"] if isinstance(row["leader_final_symbol"], str) else row["symbol"]), axis=1)
                live_pool = live_pool.merge(user_leaders.add_prefix("user_"), left_on="leader_ID", right_index=True, how='left')

                live_pool = await self.get_precisions(bot, user, live_pool)
                active_leaders = live_pool["leader_ID"].dropna().unique()
                n_leaders = active_leaders.size

                print(f'[{utils.current_readable_time()}]: Updating Positions for {n_leaders} / {len(user_leaders)} leaders')

                positions_opened_changed = live_pool.copy()[((~live_pool["leader_symbol"].isna()) | (live_pool["symbol"].isna())) & (~live_pool["final_symbol"].isin(ignored_symbols.index))]
                if len(positions_opened_changed) > 0:
                    user_leverage = user["account"]["data"]["leverage"] - 1
                    positions_closed = []
                    leader_cap = user["detail"]["data"]["TARGET_RATIO"] / user_leaders["WEIGHT"].sum()
                    leverage_ratio = user_leaders["AVERAGE_LEVERAGE"].mean() / user["account"]["data"]["leverage"]

                    positions_opened_changed["TARGET_SHARE"] = positions_opened_changed["leader_POSITION_SHARE"] * positions_opened_changed["user_WEIGHT"] * leader_cap * leverage_ratio
                    positions_opened_changed['ABSOLUTE_SHARE'] = positions_opened_changed["TARGET_SHARE"].abs()
                    positions_opened_changed['TOTAL_TARGET_SHARE'] = positions_opened_changed.groupby('final_symbol')['ABSOLUTE_SHARE'].transform('sum')
                    positions_opened_changed["POSITION_WEIGHT"] = positions_opened_changed["ABSOLUTE_SHARE"] / positions_opened_changed["TOTAL_TARGET_SHARE"]
                    positions_opened_changed["WEIGHTED_SHARP"] = positions_opened_changed['leader_SHARP'] * positions_opened_changed["POSITION_WEIGHT"]
                    positions_opened_changed["WEIGHTED_ROI"] = positions_opened_changed['leader_ROI'] * positions_opened_changed["POSITION_WEIGHT"]

                    # print(positions_opened_changed)
                    positions_opened_changed = positions_opened_changed.groupby("final_symbol").agg({
                        "symbol": 'first',
                        "leader_symbol": 'first',
                        "netAsset": 'first',
                        "borrowed": 'first',
                        "free": 'first',
                        "interest": 'first',
                        "stepSize": 'first',
                        "minQty": 'first',
                        "minNotional": 'first',
                        "leader_ID": 'unique',
                        "WEIGHTED_SHARP": 'mean',
                        "WEIGHTED_ROI": 'mean',
                        "leader_positionAmount": 'sum',
                        "leader_markPrice": 'mean',
                        "TARGET_SHARE": 'sum',
                        }).reset_index()
                    # print(positions_opened_changed)
                    positions_opened_changed = positions_opened_changed.sort_values(by=["WEIGHTED_SHARP", "WEIGHTED_ROI", "TARGET_SHARE"], ascending=False)

                    positions_opened_changed["CUMULATIVE_SHARE"] = positions_opened_changed["TARGET_SHARE"].abs().cumsum()
                    positions_opened_changed["TARGET_VALUE"] = positions_opened_changed["TARGET_SHARE"] * account_data["value_USDT"] * user_leverage

                    last_position = positions_opened_changed[positions_opened_changed['CUMULATIVE_SHARE'] > user["detail"]["data"]["TARGET_RATIO"]].iloc[0] if not positions_opened_changed[positions_opened_changed['CUMULATIVE_SHARE'] > user["detail"]["data"]["TARGET_RATIO"]].empty else pd.Series([])
                    last_symbol = last_position["symbol"] if not last_position.empty else ''

                    positions_opened_changed = positions_opened_changed.loc[positions_opened_changed["CUMULATIVE_SHARE"] <= user["detail"]["data"]["TARGET_RATIO"]]
                    user_invested_ratio = positions_opened_changed["CUMULATIVE_SHARE"].values[-1]

                    positions_closed = live_pool.copy().loc[(~live_pool["symbol"].isna()) & (~live_pool["symbol"].isin(positions_opened_changed["final_symbol"])) & (live_pool["symbol"] != last_symbol)]
                    
                    if len(positions_closed) > 0:
                        positions_closed = positions_closed.groupby('symbol').agg({
                            "netAsset": 'first',
                            "borrowed": 'first',
                            "free": 'first',
                            "stepSize": 'first',
                            "minQty": 'first',
                            "minNotional": 'first',
                        }).reset_index()

                        positions_closed = positions_closed.merge(positions_opened_changed[['final_symbol', 'leader_markPrice']], left_on='symbol', right_on='final_symbol', how='left')
                        positions_closed = await self.get_prices(bot, positions_closed, 'leader_markPrice')
                        positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE")
                        positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")

                    all_positions_open_changed = positions_opened_changed.copy()
                    # print(all_positions_open_changed)
                    if not lifecycle["reset_mix"] and account_data["collateral_margin_level"] > 1.15:
                        positions_opened_changed = positions_opened_changed[positions_opened_changed["leader_symbol"].isin(mix_diff) | positions_opened_changed["symbol"].isna()]

                    if not last_position.empty:
                        last_diff_pass = False
                        last_position["TARGET_SHARE"] = user["detail"]["data"]["TARGET_RATIO"] - user_invested_ratio
                        last_position["TARGET_VALUE"] = last_position["TARGET_SHARE"] * account_data["value_USDT"] * user_leverage
                        last_position["TARGET_VALUE"] = last_position["TARGET_VALUE"] * -1 if last_position["leader_positionAmount"] < 0 else last_position["TARGET_VALUE"]
                        last_diff_pass = abs(last_position["TARGET_VALUE"] / last_position["leader_markPrice"] - last_position["netAsset"]) / abs(last_position["netAsset"]) > 0.1 if last_position["netAsset"] else True
                        user_invested_ratio = user["detail"]["data"]["TARGET_RATIO"]
                        last_position["CUMULATIVE_SHARE"] = user_invested_ratio
                        last_position['leader_ID'] = last_position['leader_ID'].tolist()
                        # print(last_position)
                        all_positions_open_changed.loc[len(all_positions_open_changed) + 1] = last_position
                        # print(all_positions_open_changed)

                        if last_position["symbol"] == None or (last_position["final_symbol"] in mix_diff or len(positions_opened_changed) > 0) and last_diff_pass:
                            positions_opened_changed.loc[len(positions_opened_changed) + 1] = last_position

                    all_positions_open_changed = all_positions_open_changed.sort_values(by=["TARGET_VALUE"], ascending=False)
                    all_positions_open_changed["n_leaders"] = all_positions_open_changed["leader_ID"].apply(len)
                    total_value = round(all_positions_open_changed["TARGET_VALUE"].abs().sum(), 2)
                    total_share = round(all_positions_open_changed["CUMULATIVE_SHARE"].max(), 2)
                    print(all_positions_open_changed[["final_symbol", 'TARGET_SHARE', 'TARGET_VALUE', "leader_ID", "n_leaders"]].set_index('final_symbol'))
                    print(f'Total Value: {total_value} - Total Share: {total_share}')

                    opened_changed_leaders = set(np.concatenate(all_positions_open_changed["leader_ID"].values).flatten())
                    leader_entries = leader_entries.loc[leader_entries.index.isin(opened_changed_leaders)]
                    notional_balances = new_positions.groupby('ID')['NOTIONAL_BALANCE'].first()

                    for leader_id in opened_changed_leaders:
                        if leader_id not in leader_entries.index:
                            leader_entries.loc[leader_id] = notional_balances.loc[leader_id]

                    positions_opened_changed["CURRENT_VALUE"] = positions_opened_changed["netAsset"] * positions_opened_changed["leader_markPrice"]
                    positions_opened_changed["TARGET_AMOUNT"] = positions_opened_changed["TARGET_VALUE"] / positions_opened_changed["leader_markPrice"]

                    positions_opened_changed = self.validate_amounts(positions_opened_changed, "netAsset", "CURRENT_VALUE")
                    positions_opened_changed = self.validate_amounts(positions_opened_changed, "TARGET_AMOUNT", "TARGET_VALUE")

                positions_opened = positions_opened_changed.copy()[(positions_opened_changed["TARGET_AMOUNT_PASS"]) & ((positions_opened_changed["symbol"].isna()) | (~positions_opened_changed["netAsset_PASS"]))].set_index("final_symbol")

                positions_changed = positions_opened_changed.copy()[(positions_opened_changed["TARGET_AMOUNT_PASS"]) & (~positions_opened_changed["symbol"].isna()) & (positions_opened_changed["netAsset_PASS"])]
                if len(positions_changed) > 0:
                    positions_changed["DIFF_AMOUNT"] = positions_changed["TARGET_AMOUNT"] - positions_changed["netAsset"]
                    positions_changed["DIFF_VALUE"] = positions_changed["TARGET_VALUE"] - positions_changed["CURRENT_VALUE"]
                    positions_changed = self.validate_amounts(positions_changed, "DIFF_AMOUNT", "DIFF_VALUE")
                    positions_changed = positions_changed[positions_changed["DIFF_AMOUNT_PASS"]].set_index("final_symbol")

                    positions_changed["DIFF_VALUE_ABS"] = positions_changed["DIFF_VALUE"].abs()
                    positions_changed = positions_changed.sort_values(by=["DIFF_VALUE_ABS"], ascending=False)
                
                    positions_changed["OPEN"] = ((positions_changed["DIFF_AMOUNT"] > 0) & (positions_changed["TARGET_AMOUNT"] > 0)) | ((positions_changed["DIFF_AMOUNT"] < 0) & (positions_changed["TARGET_AMOUNT"] < 0))
                    positions_changed["SWITCH_DIRECTION"] = ((positions_changed["netAsset"] > 0) & (positions_changed["TARGET_AMOUNT"] < 0)) | ((positions_changed["netAsset"] < 0) & (positions_changed["TARGET_AMOUNT"] > 0))
                    
                if any([len(positions_opened) > 0, len(positions_closed) > 0, len(positions_changed) > 0]): #, len(positions_excess) > 0
                    lifecycle["tick_boost"] = True

                    levered_ratio = user_invested_ratio * user_leverage

                    print(f'[{utils.current_readable_time()}]: Updated Positions - Invested: {round(user_invested_ratio * 100) / 100} - Levered: {round(levered_ratio * 100) / 100}')

                    account_data.update({
                        "levered_ratio": levered_ratio,
                        "unlevered_ratio": user_invested_ratio,
                    })
            else:
                print(f'[{utils.current_readable_time()}]: Updating Positions')

                positions_closed = live_pool.copy()
                positions_closed = await self.get_prices(bot, positions_closed)
                positions_closed = self.validate_amounts(positions_closed, "netAsset", "CURRENT_VALUE")
                positions_closed = positions_closed[positions_closed["netAsset_PASS"]].set_index("symbol")

                positions_opened = []
                positions_changed = []
                n_leaders = 0
                active_leaders = []
            
            account_data.update({
                "n_leaders": n_leaders,
                "active_leaders": list(active_leaders)
            })
            user_account_update = {
                "account": account_data,
                "positions": user_positions.set_index("asset").to_dict(),
                "entries": leader_entries.to_dict()
            }

            return user_account_update, positions_closed, positions_opened, positions_changed, positions_excess, dropped_leaders
        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_update', None)


    async def user_account_close(self, bot, user, new_user_mix, dropped_leaders, lifecycle):
        try:
            user_account_update = {
                "mix": new_user_mix,
   
            }

            if lifecycle["reset_mix"]:
                user_account_update.update({
                    "account": {
                        "reset_mix": False
                    }
                })   
                
            if len(dropped_leaders) > 0:
                user_leaders = user["leaders"]["data"]

                for binance_id in dropped_leaders:
                    user_leaders["WEIGHT"].pop(binance_id)

                user_account_update.update({"leaders": user_leaders})

            return user_account_update
        except Exception as e:
            await self.handle_exception(bot, user, e, 'user_account_close', None)
    

    async def repay_position(self, bot, user, asset, amount:float, position):
        # weight = 3000
        try:
            if asset == 'USDT' and amount > 5 or asset != 'USDT':
                self.client.borrow_repay(asset=asset, symbol=asset + 'USDT', amount=amount, type='REPAY', isIsolated='FALSE')
                await self.app.log.create(bot, user, 'INFO', 'REPAY', 'TRADE', f'Repayed Position: {asset} - {amount}', details=position.to_dict())
        except Exception as error:
            await self.handle_exception(bot, user, error, f'repay_position {asset} - {amount}', asset, position=str(position), notify=False)

    
    async def open_position(self, bot, user, symbol:str, amount, position, user_mix, source, reverse=False, retry=False):
        # weight = 6
        try:
            amount = amount * -1 if reverse else amount
            side = 'SELL' if amount < 0 else 'BUY'
            side_effect = 'AUTO_BORROW_REPAY' if retry else 'MARGIN_BUY'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType=side_effect)
            # print(response)
            if float(response["executedQty"]) / abs(amount) < 0.9:
                user_mix["BAG"].pop(symbol)

            await self.app.log.create(bot, user, 'INFO', source, 'TRADE', f'Opened Position: {symbol} - {amount} / {round(position["TARGET_VALUE"], 2)}', details=str(position.to_dict()))
        except Exception as error:
            if error.args[1] == -2010 and not retry:
                await self.open_position(bot, user, symbol, amount, position, user_mix, f'{source} - AUTO', retry=True)
            if error.args[1] == -3045 or error.args[1] == 51097 or error.args[1] == -3021:
                if "ignored_symbols" in user["account"]["data"].keys():
                    ignored_symbols = pd.DataFrame(user["account"]["data"]["ignored_symbols"])
                else:
                    ignored_symbols = pd.DataFrame(columns=["symbol", "time"]).set_index("symbol")
                ignored_symbols.loc[symbol] = utils.current_time()
                user_update = {
                    "account": {
                        "ignored_symbols": ignored_symbols.to_dict()
                    }
                }
                await self.app.database.update(user, user_update, 'users')
            else:
                await self.handle_exception(bot, user, error, f'{source}: {symbol} - {amount} / {round(position["TARGET_VALUE"], 2)}', symbol, user_mix=user_mix, position=position)


    async def close_position(self, bot, user, symbol, amount, position, user_mix, source, reverse=False, retry=False):
        # weight = 6
        try:
            amount = amount * -1 if reverse else amount
            side = 'SELL' if amount < 0 else 'BUY'
            side_effect = 'AUTO_BORROW_REPAY' if retry else 'AUTO_REPAY'

            response = self.client.new_margin_order(symbol=symbol, quantity=abs(amount), side=side, type='MARKET', sideEffectType=side_effect)
            # print(response)
            if float(response["executedQty"]) / abs(amount) < 0.9:
                user_mix["BAG"].pop(symbol)

            await self.app.log.create(bot, user, 'INFO', source, 'TRADE', f'Closed Position: {symbol} - {amount} / {round(position["TARGET_VALUE"], 2)}', str(position.to_dict()))
        except Exception as error:
            if error.args[1] == -2010 and not retry:
                await self.close_position(bot, user, symbol, amount, position, user_mix, f'{source} - AUTO', retry=True)
            else:
                await self.handle_exception(bot, user, error, f'{source}: {symbol} - {amount} / {round(position["TARGET_VALUE"], 2)}', symbol, user_mix=user_mix, position=position)


    async def handle_exception(self, bot, user, error, source, symbol, user_mix=None, position=None, notify=True):
        trace = traceback.format_exc()
        print(trace)
        if user_mix and symbol in user_mix.keys():
            user_mix["BAG"].pop(symbol)
        
        await self.app.log.create(bot, user, 'ERROR', source, 'TRADE', message=f'Error in Binance API: {symbol} - {error}', details=position, error=trace, notify=notify)
