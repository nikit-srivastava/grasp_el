from typing import Any

from pydantic import BaseModel

from grasp.configs import NotesGenerateQuestionsConfig
from grasp.model import Message
from grasp.tasks.base import GraspTask
from grasp.tasks.functions import find_frequent, find_frequent_function_definition
from grasp.tasks.question_generation.functions import (
    function_definitions,
    show_questions,
    submit_question,
)
from grasp.utils import format_list


class QuestionGenerationState(BaseModel):
    questions: dict[str, list[str]] = {}


def rules() -> list[str]:
    return [
        "Prioritize diversity in topic, difficulty, and style over correctness "
        "or guaranteed answerability. Real users sometimes ask questions a knowledge "
        "graph cannot fully answer; emulating that variety is part of the goal.",
        "Verifying that a question is answerable is optional. You may validate "
        "the existence of related entities or properties, or draft and execute a "
        "SPARQL query to soft-verify, but you may also submit purely speculative "
        "questions without verification.",
        "Aim for a roughly equal distribution of questions across the available "
        "knowledge graphs. Where appropriate, you may also submit questions "
        "that span multiple knowledge graphs.",
    ]


def system_information(config: NotesGenerateQuestionsConfig) -> str:
    return f"""\
You are emulating a user posing questions over the available knowledge graphs. \
Your task is to produce a diverse pool of plausible user questions \
that real users might ask, with the help of the provided functions.

You should follow a step-by-step approach:
1. Look at the existing questions to see what is already \
in the pool and identify underrepresented topics, difficulties, or styles.
2. Come up with a candidate user question targeting an underrepresented angle. \
If needed, explore the knowledge graph using the provided functions to gain \
inspiration.
3. Submit the question once you are happy with it.
4. Repeat steps 1-3 until you have submitted around {config.questions_per_round} \
questions for this round, then stop."""


def output(state: QuestionGenerationState) -> dict:
    kg_questions = []
    for kg, questions in state.questions.items():
        kg_questions.append(f'Questions for "{kg}":\n' + format_list(questions))

    formatted = "\n\n".join(kg_questions)

    return {
        "type": "output",
        "questions": {kg: list(qs) for kg, qs in state.questions.items()},
        "formatted": formatted,
    }


class QuestionGenerationTask(GraspTask):
    name = "question_generation"

    def system_information(self) -> str:
        assert isinstance(self.config, NotesGenerateQuestionsConfig)
        return system_information(self.config)

    def rules(self) -> list[str]:
        return rules()

    def function_definitions(self) -> list[dict]:
        kgs = [m.kg for m in self.managers]
        functions = function_definitions(kgs)
        functions.append(find_frequent_function_definition(kgs, self.config.list_k))
        return functions

    def call_function(
        self,
        fn_name: str,
        fn_args: dict,
        known: set[str],
        example_indices: dict | None,
    ) -> str:
        assert isinstance(self.config, NotesGenerateQuestionsConfig)
        assert self.state is not None, (
            "State must be provided for question generation task"
        )

        if fn_name == "stop":
            return "Stopping question generation."

        elif fn_name == "submit_question":
            return submit_question(
                self.state.questions,
                fn_args["kg"],
                fn_args["question"],
            )

        elif fn_name == "show_questions":
            return show_questions(
                self.state.questions,
                fn_args["kg"],
                fn_args["page"],
                self.config.list_k,
            )

        elif fn_name == "find_frequent":
            return find_frequent(
                self.managers,
                fn_args["kg"],
                fn_args["position"],
                fn_args.get("subject"),
                fn_args.get("property"),
                fn_args.get("object"),
                fn_args.get("page", 1),
                self.config.list_k,
                known,
                self.config.sparql_request_timeout,
                self.config.sparql_read_timeout,
            )

        raise ValueError(f"Unknown function {fn_name}")

    def done(self, fn_name: str) -> bool:
        return fn_name == "stop"

    def setup(self, input: Any) -> str:
        assert isinstance(input, QuestionGenerationState), (
            "Input for question generation must be a QuestionGenerationState"
        )
        self.state = input
        return "Generate plausible user questions for the available knowledge graphs."

    def output(self, messages: list[Message]) -> dict:
        return output(self.state)
