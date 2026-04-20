"""This script creates derivative category CSV database files from the main
'aircraft-taxonomy-db.csv' database file. The categories are created based on the 'CMPG'
column.
"""

import logging

import pandas as pd

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s", level=logging.INFO
)

if __name__ == "__main__":
    logging.info("Reading the main csv file...")
    unsort_df = pd.read_csv("data/aircraft-taxonomy-db.csv")
    df = unsort_df.sort_values(by=["$ICAO"], ascending=True)
    df.to_csv(
        "data/aircraft-taxonomy-db.csv",
        mode="w",
        index=False,
        header=True,
        encoding="utf8",
        lineterminator="\n",
    )
    logging.info("Main csv file read and sorted successfully.")

    logging.info("Creating the category CSV files...")
    for category in df["#CMPG"].unique():
        if pd.isna(category):  # Skip N/A values.
            continue

        # Create category CSV files.
        logging.info(f"Creating the '{category}' category CSV file...")
        category_df = df[df["#CMPG"] == category]
        category_df.to_csv(
            f"data/aircraft-taxonomy-{category.lower()}.csv",
            index=False,
            mode="w",
            encoding="utf8",
            lineterminator="\n",
        )
    logging.info("Category CSV files created successfully.")
