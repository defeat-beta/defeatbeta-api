import datasets

from defeatbeta_api.client.hugging_face_client import get_dataset
from defeatbeta_api.utils.const import stock_prices

datasets.utils.logging.set_verbosity_debug()

dataset = get_dataset(stock_prices)

# Inspect available splits
print(dataset)

# Access the 'train' split (or whichever split is available)
ds = dataset["train"]

# split train and test80% / 20%
split_datasets = ds.train_test_split(test_size=0.2, seed=0xDEADBEAF)

# split_datasets
print(split_datasets)