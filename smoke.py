"""Smoke test: does Inspect talk to the model at all? Not part of the eval."""
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import includes
from inspect_ai.solver import generate, system_message


@task
def smoke():
    return Task(
        dataset=MemoryDataset([
            Sample(input="What is the capital of Poland? Answer with one word.", target="Warsaw"),
        ]),
        solver=[system_message("You are terse."), generate()],
        scorer=includes(),
    )
