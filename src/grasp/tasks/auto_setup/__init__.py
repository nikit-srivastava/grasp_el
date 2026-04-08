from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from grasp.manager import KgManager
from grasp.manager.utils import (
    get_common_sparql_prefixes,
    load_kg_index_sparqls,
    load_kg_info,
    load_kg_info_sparqls,
    merge_prefixes,
)
from grasp.model import Message
from grasp.sparql.utils import (
    load_entity_index_sparql,
    load_entity_info_sparql,
    load_property_index_sparql,
    load_property_info_sparql,
)
from grasp.tasks.auto_setup.functions import (
    INDEX_SPARQL_VARS,
    INFO_SPARQL_VARS,
    setup_functions,
    validate_sparql,
)
from grasp.tasks.base import GraspTask
from grasp.tasks.functions import find_frequent, find_frequent_function_definition
from grasp.utils import FunctionCallException, format_prefixes


class AutoSetupState(BaseModel):
    ent_index_sparql: str | None = None
    prop_index_sparql: str | None = None
    ent_info_sparql: str | None = None
    prop_info_sparql: str | None = None
    prefixes: dict[str, str] = {}
    description: str | None = None


def load_initial_state(manager: KgManager) -> AutoSetupState:
    ent_index_sparql, prop_index_sparql = load_kg_index_sparqls(manager.kg)
    ent_info_sparql, prop_info_sparql = load_kg_info_sparqls(manager.kg)
    prefixes, desc = load_kg_info(manager.kg)

    return AutoSetupState(
        ent_index_sparql=ent_index_sparql,
        prop_index_sparql=prop_index_sparql,
        ent_info_sparql=ent_info_sparql,
        prop_info_sparql=prop_info_sparql,
        prefixes=prefixes,
        description=desc,
    )


def format_query(manager: KgManager, query: str | None) -> str:
    if query is None:
        return "None"

    return manager.fix_prefixes(query, remove_known=True)


def format_state(state: AutoSetupState, manager: KgManager) -> str:
    parts = []
    parts.append(f"Description:\n{state.description}")
    parts.append(f"Prefixes:\n{format_prefixes(state.prefixes)}")
    parts.append(
        f"Entity index SPARQL:\n{format_query(manager, state.ent_index_sparql)}"
    )
    parts.append(f"Entity info SPARQL:\n{format_query(manager, state.ent_info_sparql)}")
    parts.append(
        f"Property index SPARQL:\n{format_query(manager, state.prop_index_sparql)}"
    )
    parts.append(
        f"Property info SPARQL:\n{format_query(manager, state.prop_info_sparql)}"
    )

    fmt = f'Current setup for "{manager.kg}" at {manager.endpoint}:\n\n'
    fmt += "\n\n".join(parts)
    return fmt


class AutoSetupTask(GraspTask):
    name = "auto-setup"

    def system_information(self) -> str:
        manager = self.managers[0]
        return f"""\
You are a knowledge graph setup assistant. Your task is to explore \
a SPARQL endpoint and determine the appropriate knowledge graph setup. \
The setup includes the following components (some of which may alreay be \
populated with values from previous setup runs):
1. Index SPARQL queries for entities and properties, which are used to build search indices. \
2. Info SPARQL queries for entities and properties, which are used to retrieve additional information \
for search function call results.
3. Prefixes specific to the knowledge graph for use in function calls.
4. A description of the knowledge graph.

You should follow a step-by-step approach:
1. Look at and understand the current state of the setup.
2. Explore the knowledge graph and find ways to improve the current setup. For components 1 and 2, \
think about what entities and properties you would like to be able to search for, and what \
additional information you would like to have for them in search results to support \
disambiguation and provide context. For components 3 and 4, check whether they \
are accurate and complete. If you encounter IRI namespaces not yet covered by the current prefixes, \
add them to the prefixes. If you find that information in the description is missing or outdated, \
update it.
3. Update the setup as needed. Make sure to validate and execute any SPARQL queries against \
the knowledge graph before setting them. Go back to step 2 and repeat if there are \
still improvements to be made.
4. Finalize the setup and stop.

Below are generic index and info SPARQL queries that you can use as a starting point \
and reference. They are used as default queries if no specific queries have been set yet, \
but may not be optimal and can often be improved.

Entity index SPARQL:
{format_query(manager, load_entity_index_sparql())}

Entity info SPARQL:
{format_query(manager, load_entity_info_sparql())}

Property index SPARQL:
{format_query(manager, load_property_index_sparql())}

Property info SPARQL:
{format_query(manager, load_property_info_sparql())}"""

    def rules(self) -> list[str]:
        return [
            "Keep the index SPARQL queries efficient as they will be run over the "
            "entire knowledge graph to build search indices. They will often time out "
            "if you test them as is but should still be validated to the extent "
            "possible, for example by restricting to a set of specific IRIs "
            "or by testing query components separately.",
            "Sometimes properties do not have any associated literals that "
            "can be used to search them. If you want them to be searchable anyway, just make sure "
            "that their IRIs are in the index SPARQL results (with unbound or empty ?value). "
            "For properties the IRIs (without prefix) themselves are always indexed on top of any literal values.",
            "The infos retrieved per IRI should be limited to the most important ones (10 or fewer). Their purpose "
            "is to provide a concise signal for disambiguation, not to provide a complete list of all associated information.",
            "Make sure to respect the user notes regarding the setup if provided.",
        ]

    def function_definitions(self) -> list[dict]:
        kgs = [m.kg for m in self.managers]
        return [
            find_frequent_function_definition(kgs),
            *setup_functions(),
        ]

    def call_function(
        self,
        fn_name: str,
        fn_args: dict,
        known: set[str],
        example_indices: dict | None,
    ) -> str:
        assert self.state is not None
        manager = self.managers[0]

        if fn_name == "find_frequent":
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

        elif fn_name == "set_query":
            return self.set_query(manager, **fn_args)

        elif fn_name == "set_prefix":
            return self.set_prefix(manager, **fn_args)

        elif fn_name == "set_description":
            manager.description = fn_args["description"]
            return "Description updated"

        elif fn_name == "stop":
            return "Stopping"

        raise FunctionCallException(f"Unknown function {fn_name}")

    def set_query(self, manager: KgManager, index: str, type: str, sparql: str) -> str:
        vars = INFO_SPARQL_VARS if type == "info" else INDEX_SPARQL_VARS

        try:
            validate_sparql(manager, sparql, vars)
        except ValueError as e:
            raise FunctionCallException(
                f"Invalid {index} {type} SPARQL:\n{str(e)}"
            ) from e

        if index == "entity" and type == "info":
            manager.entity_info_sparql = sparql
            self.state.ent_info_sparql = sparql
        elif type == "info":
            manager.property_info_sparql = sparql
            self.state.prop_info_sparql = sparql
        elif index == "entity":
            self.state.ent_index_sparql = sparql
        else:
            self.state.prop_index_sparql = sparql

        msg = f"{index.capitalize()} {type} SPARQL updated"
        if type == "info":
            msg += " and used in subsequent function calls"
        return msg

    def set_prefix(self, manager: KgManager, short: str, namespace: str) -> str:
        try:
            prefixes = deepcopy(self.state.prefixes)
            prefixes[short] = namespace

            merged, _, kg_prefixes = merge_prefixes(
                get_common_sparql_prefixes(),
                prefixes,
                manager.logger,
                do_raise=True,
            )
        except RuntimeError as e:
            raise FunctionCallException(str(e)) from e

        self.state.prefixes = kg_prefixes
        manager.kg_prefixes = kg_prefixes
        manager.prefixes = merged
        return "Prefixes updated and available for subsequent function calls."

    def done(self, fn_name: str) -> bool:
        return fn_name == "stop"

    def setup(self, input: Any) -> str:
        assert input is None or isinstance(input, str), (
            "Input for auto-setup must be None or a string (user notes)"
        )
        self.state = load_initial_state(self.managers[0])
        formatted = format_state(self.state, self.managers[0])
        formatted += f"\n\nUser notes:\n{input}"
        return formatted

    def output(self, messages: list[Message]) -> dict:
        assert self.state is not None
        manager = self.managers[0]
        return {
            "type": "output",
            "kg": manager.kg,
            "endpoint": manager.endpoint,
            "entities": {
                "index": self.state.ent_index_sparql,
                "info": self.state.ent_info_sparql,
            },
            "properties": {
                "index": self.state.prop_index_sparql,
                "info": self.state.prop_info_sparql,
            },
            "description": self.state.description,
            "prefixes": self.state.prefixes,
            "formatted": format_state(self.state, manager),
        }
