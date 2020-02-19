# from Prescient import db
import pandas as pd
import os
import sqlite3
MAIN_DATABASE = os.path.abspath(os.path.join(__file__, "../..", "MainDB.db"))
PRICE_DATABASE = os.path.abspath(os.path.join(__file__, "../..", "Security_PricesDB.db"))

## To get data from the DB its
# x = pd. read_sql(sql=query, con=db.engine)
# to get mainDB db.engine
# to get pricesDB db.get_engine(app, "Security_PricesDB")
#ive tested this in terminal and it works

class Portfolio_Performance(object):
    """docstring for Portfolio_Performance."""

    def __init__(self, user_id):
        self.user_id = user_id

    def get_quantity_cumsum(self, ticker):
        # Gets the cumulative summed quantity per date for each security
        conn = sqlite3.connect(MAIN_DATABASE)
        query = """Select DATE(created_timestamp), quantity
        From watchlist_securities
        where user_id =:user_id and ticker=:ticker
        ORDER BY created_timestamp """
        params = {"user_id": self.user_id, "ticker": ticker}

        df = pd.read_sql_query(query, conn, params=params)
        df["quantity"] = df["quantity"].cumsum()
        return df.to_numpy().tolist()

    def get_daily_mv(self, ticker):

        watchlist = self.get_quantity_cumsum(ticker)
        conn = sqlite3.connect(PRICE_DATABASE)
        query = f"""SELECT * FROM {ticker}"""

        df = pd.read_sql_query(query, conn, index_col="index")

        df["quantity"] = float("nan")
        df["market_val"] = float("nan")

        start_date = watchlist[0][0]

        df2 = df.loc[start_date:]  # the prices starting from the first date the security was held
        df2 = df2.copy()  # prevents chain assignment
        for i in watchlist:
            df2.at[i[0], "quantity"] = i[1]  # at the date, insert quantity

        df2["price"] = df2["price"].fillna(method="ffill")
        df2["quantity"] = df2["quantity"].fillna(method="ffill")

        df2["price"] = pd.to_numeric(df2["price"])
        df2["market_val"] = round((df2["price"] * df2["quantity"]),3)

        df2 = df2[["market_val"]]
        new_name = f"market_val_{ticker}"
        df2 = df2.rename(columns={"market_val": new_name})
        # with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
        #     print(df2)
        return df2

    def full_table(self):
        conn = sqlite3.connect(MAIN_DATABASE)
        distinct_query = """SELECT DISTINCT ticker
                            FROM watchlist_securities
                            WHERE user_id=:user_id
                            ORDER BY created_timestamp"""
        params = {"user_id": self.user_id}
        c = conn.cursor()
        result = c.execute(distinct_query, params).fetchall()
        c.close()
        conn.close()

        unique_tickers = [ticker[0] for ticker in result]

        df = pd.DataFrame()
        for ticker in unique_tickers:
            if df.empty:
                df = self.get_daily_mv(ticker)

            else:
                df_new = self.get_daily_mv(ticker)
                df = df.join(df_new)

        df = df.fillna(method="ffill")
        # with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
        #     print(p)
        return df

    def summed_table(self):
        table = self.full_table()
        table["portfolio_val"] = table.sum(axis=1)
        table = table[["portfolio_val"]]  # The daily portfolio valuations excluding flows

        conn = sqlite3.connect(MAIN_DATABASE)
        query= """SELECT
                    DATE(created_timestamp) as 'index',
                    SUM(quantity * price) as flow
                  FROM watchlist_securities
                  WHERE user_id =:user_id
                  GROUP BY DATE(created_timestamp)
                  ORDER BY DATE(created_timestamp)"""
        params = {"user_id": self.user_id}
        df = pd.read_sql_query(query, conn, index_col="index", params=params)  # inflows/outflows
        table = table.join(df)
        table = table.reset_index()

        table["flow"] = table["flow"].shift(-1)  # shifts the flows back by previous day to allow us to get the previous day valuation including flows
        table["flow"] = table["flow"].fillna(value=0)
        table["total_portfolio_val"] = table.sum(axis=1)
        table["pct_change"] = (((table["portfolio_val"].shift(-1)/(table["total_portfolio_val"]))-1)*100)
        table["pct_change"] = round(table["pct_change"].shift(1), 2)
        # with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
        #     print(table)
        table = list(table.itertuples(index=False))
        return table  # changes df to  named tuples so it can be rendered


class Portfolio_Summaries(object):
    def __init__(self, user_id):
        self.user_id = user_id

    def summary_table(self):
        query = """SELECT
                ticker,
                SUM(units) as quantity,
                ROUND(AVG(price),2) as price
            FROM
                (SELECT
                    a.user_id,
                    a.ticker,
                    CASE WHEN a.quantity < 0 THEN SUM(a.quantity) ELSE 0 END AS 'units',
                    CASE WHEN a.quantity < 0 THEN SUM(a.quantity*a.price)/SUM(a.quantity) ELSE 0 END AS 'price'
                FROM watchlist_securities a
                WHERE a.quantity < 0 and user_id=:user_id
                GROUP BY a.ticker
                HAVING 'price' > 0

                UNION ALL
                SELECT
                    b.user_id,
                    b.ticker,
                    CASE WHEN b.quantity > 0 THEN SUM(b.quantity) ELSE 0 END AS 'units',
                    CASE WHEN b.quantity > 0 THEN SUM(b.quantity*b.price)/SUM(b.quantity) ELSE 0 END AS 'price'
                FROM watchlist_securities b
                WHERE b.quantity > 0 and user_id=:user_id
                GROUP BY b.ticker
                HAVING 'price' > 0)
                WHERE user_id=:user_id
                GROUP BY ticker"""
        conn = sqlite3.connect(MAIN_DATABASE)
        conn.row_factory = sqlite3.Row
        params = {"user_id": self.user_id}
        c = conn.cursor()
        result = c.execute(query, params).fetchall()
        c.close()
        conn.close()

        return result

    def get_pie_chart(self):
        query = """SELECT ticker, ROUND(ABS(SUM(quantity*price)/t.s)*100,2) as "Market_val_perc"
        from watchlist_securities
        CROSS JOIN (SELECT SUM(quantity*price) AS s FROM watchlist_securities WHERE user_id=:user_id) t
        WHERE user_id=:user_id
        GROUP BY ticker"""
        conn = sqlite3.connect(MAIN_DATABASE)
        conn.row_factory = sqlite3.Row
        params = {"user_id": self.user_id}
        c = conn.cursor()
        result = c.execute(query, params).fetchall()
        c.close()
        conn.close()
        return result

    def get_bar_chart(self):
        query = """SELECT ticker, ROUND(ABS(SUM(quantity*price)),2) as "Market_val"
                    from watchlist_securities
                    WHERE user_id=:user_id
                    GROUP BY ticker
                    LIMIT 5"""
        conn = sqlite3.connect(MAIN_DATABASE)
        conn.row_factory = sqlite3.Row
        params = {"user_id": self.user_id}
        c = conn.cursor()
        result = c.execute(query, params).fetchall()
        c.close()
        conn.close()
        return result