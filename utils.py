#!/usr/bin/env python3
import numpy as np
from typing import Callable, List, NewType, Any, Dict
from tokenizers import Tokenizer
from transformers import AutoTokenizer
import torch
from enum import Enum


# from torch.utils.data import Dataset as TorchDataset
# from datasets import Dataset as Dataset, load_dataset
from torch.utils.data import DataLoader
from datasets import load_dataset

IMAGE_DIM = 32
IMAGE_LEN = IMAGE_DIM * IMAGE_DIM
NUM_COLORS = 512


InputDataClass = NewType("InputDataClass", Any)


PIXEL_TOKENS = [f"[{i:0>3}]" for i in range(NUM_COLORS)]
IMAGE_TOKEN = "[Image]"
IMAGE_FIRST_TOKEN = "[ImageFirst]"
TEXT_TOKEN = "[Text]"
TEXT_FIRST_TOKEN = "[TextFirst]"


PromptType = Enum("PrompType", ["ImagePrompt", "TextPrompt"])


def get_custom_collater(
    tokenizer: Tokenizer, rng: np.random.Generator, p: float = 0.5
) -> Callable:
    def _collater(
        features: List[InputDataClass],
    ) -> Dict[str, Any]:
        """Generate tokenized training data.

        First generate data with special tokens randomly.
        Second create image mask from the generated data.
        Third Tokenize the generated data.


        input:
        batch_images: batch of strings
        batch_captions: batch of captions (either strings or list of strings)
        p: percentage of Prompts of type TextPrompt, should be in [0.0, 1.0)
        """
        batch = {}

        assert 0.0 <= p <= 1.0, f"p should be in [0.0, 1.0], got {p}"

        prompts, image_masks = [], []
        image_start_positions = []

        batch_images = [b["palette_images"] for b in features]
        batch_captions = [b["captions"] for b in features]

        kinds = []
        for image, captions in zip(batch_images, batch_captions):
            coin_toss = rng.random() > (1.0 - p)

            caption = captions if type(captions) is str else rng.choice(captions)

            prompt = (
                f"{TEXT_FIRST_TOKEN}{caption}{IMAGE_TOKEN}{image}"
                if coin_toss
                else f"{IMAGE_FIRST_TOKEN}{image}{TEXT_TOKEN}{caption}"
            )

            image_start_position = (
                3
                + len(
                    tokenizer.tokenize(caption)
                )  # 3 corresponds to </s> and [TextFirst] and [Image]
                if coin_toss
                else 2  # 2 corresconds to </s> and [ImageFirst]
            )

            kinds.append(1 if coin_toss else 0)
            image_start_positions.append(image_start_position)
            prompts.append(prompt)

        prompts = tokenizer(prompts, return_tensors="pt", padding=True)
        batch["input_ids"] = prompts["input_ids"]
        batch["attention_mask"] = prompts["attention_mask"]

        image_masks = torch.zeros(size=batch["attention_mask"].shape, dtype=bool)

        for image_mask, image_start_position in zip(image_masks, image_start_positions):
            image_mask[image_start_position : image_start_position + IMAGE_LEN] = True

        batch["image_masks"] = image_masks
        batch["kinds"] = torch.tensor(kinds, dtype=torch.long)

        return batch

    return _collater


def prepare_tokenizer(tokenizer: Tokenizer) -> Tokenizer:
    """Prepare tokenizer."""
    tokenizer.add_tokens(PIXEL_TOKENS)
    tokenizer.add_tokens([IMAGE_FIRST_TOKEN, TEXT_FIRST_TOKEN, IMAGE_TOKEN, TEXT_TOKEN])
    return tokenizer


if __name__ == "__main__":
    d = load_dataset("h4rr9/cifar_10_palette")

    rng = np.random.default_rng()
    tok = prepare_tokenizer(AutoTokenizer.from_pretrained("facebook/opt-125m"))

    c = get_custom_collater(tok, rng, p=0.75)

    dl = DataLoader(d["train"], shuffle=True, collate_fn=c, batch_size=2)