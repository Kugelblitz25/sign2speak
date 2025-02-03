import json
from collections import namedtuple

import pandas as pd
import torch
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader
from tqdm import tqdm

from models.extractor.dataset import WLASLDataset
from models.extractor.model import ModifiedI3D
from utils.config import Config
from utils.model import create_path, load_model_weights

csvPaths = namedtuple("Paths", ["train", "test", "val"])


def extract_features(
    model, dataloader: DataLoader, save_path_train: str, save_path_test: str
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    save_path_train = create_path(save_path_train)
    save_path_test = create_path(save_path_test)
    all_features = []
    all_video_ids = []

    model.eval()
    with torch.no_grad():
        for batch_idx, (inputs, labels) in enumerate(
            tqdm(dataloader, desc="Feature Extraction")
        ):
            inputs, labels = inputs.to(device), labels.to(device)
            features, _ = model(inputs)
            features = features.cpu().numpy()

            # Get video IDs for this batch
            start_idx = batch_idx * dataloader.batch_size
            end_idx = start_idx + inputs.size(0)
            batch_video_ids = [
                dataloader.dataset.data[i]["video_id"]
                for i in range(start_idx, min(end_idx, len(dataloader.dataset)))
            ]

            # Store features and metadata
            all_features.extend(features)
            all_video_ids.extend(batch_video_ids)

    feature_cols = [f"feature_{i}" for i in range(features.shape[1])]
    df = pd.DataFrame(all_features, columns=feature_cols)
    df["video_id"] = all_video_ids
    video_to_gloss = {
        item["video_id"]: item["gloss"] for item in dataloader.dataset.data
    }
    df["gloss"] = df["video_id"].map(video_to_gloss)

    xtrain, xval = train_test_split(df, test_size=0.2)
    xtrain.to_csv(save_path_train, index=False)
    xval.to_csv(save_path_test, index=False)
    print(f"Features saved to {save_path_train} and {save_path_test}")


def main(
    data_path: csvPaths,
    num_words: int,
    video_root: str,
    weights: str,
    save_path: csvPaths,
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using Device: {device}")

    with open(data_path) as f:
        data = json.load(f)

    dataset = WLASLDataset(data, video_root)
    dataloader = DataLoader(dataset, batch_size=4, shuffle=False, num_workers=4)

    model = ModifiedI3D(num_words).to(device)
    model = load_model_weights(model, weights, device)
    print(f"Num Classes: {num_words}")

    extract_features(model, dataloader, save_path_train, save_path_test)


if __name__ == "__main__":
    config = Config("Feature Generation for Spectrogram Generation")

    main(
        config.data.processed.csvs,
        config.n_words,
        config.data.processed.videos,
        config.transformer.extractor_weights,
        config.data.processed.vid_features,
    )
