from datasets import load_dataset
import datasets

datasets.utils.logging.set_verbosity_debug()

dataset = load_dataset(
    "bwzheng2010/yahoo-finance-data",
    data_files="data/stock_prices.parquet"
)

# Inspect available splits
print(dataset)

# Access the 'train' split (or whichever split is available)
ds = dataset["train"]

# split train and test80% / 20%
split_datasets = ds.train_test_split(test_size=0.2, seed=0xDEADBEAF)

# split_datasets
print(split_datasets)