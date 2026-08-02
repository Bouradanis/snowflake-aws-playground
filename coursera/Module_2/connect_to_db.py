import snowflake.snowpark as snowpark
from snowflake.snowpark import Session
from dotenv import load_dotenv
import os
import pandas as pd

#load_dotenv('C:\Git_Repos\ey-data-challenge-2026\.env')  # for Windows
load_dotenv('/mnt/c/Git_Repos/ey-data-challenge-2026/.env')  # for Ubuntu env


def main(session: snowpark.Session):
    df_table = session.table("TASTY_BYTES.RAW_POS.MENU")
    #df_table.show()

    df_pandas = df_table.to_pandas()
    df_pandas.to_csv("menu_data_ds.csv", index=False)
    print(df_pandas.head())

    return df_table


if __name__ == "__main__":
    connection_parameters = {
        "account": os.environ.get("ACCOUNT"),
        "user": os.environ.get("USER"),
        "password": os.environ.get("ACCOUNT_PASSWORD"),
        "warehouse": "compute_wh",
        "database": "TASTY_BYTES",
        "schema": "RAW_POS"
    }

    session = Session.builder.configs(connection_parameters).create()

    try:
        result = main(session)
        print("Script completed successfully")
    finally:
        session.close()