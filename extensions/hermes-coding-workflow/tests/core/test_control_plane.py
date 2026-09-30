from hermes_coding_workflow.contracts import PROFILES,STAGES,validate_design,validate_plan,validate_review,validate_record

def test_v1_contracts_are_strict() -> None:
    assert not validate_design({"approved": True})
    design={"observable_outcome":"works","requirements":[{"id":"R1","description":"x"}],"acceptance_criteria":["pass"],"approved":True}
    assert validate_design(design)
    assert not validate_plan({"tasks":[],"approved":True},{"R1"})
    assert not validate_plan({"tasks":[{"id":"1","description":"do x","paths":["src/x.py"],"test_command":["python","-m","pytest"],"requirement_ids":["R1"]}],"approved":True},{"R1"})
    assert not validate_review({"reviewed_sha":"a"*40,"decision":"approved","findings":[1],"dispositions":[]})
    assert tuple(PROFILES) == STAGES
    assert validate_record({"schema_version":"hcw/v1","kind":"run","id":"bad","revision":0}) == "malformed_schema"


def test_review_contract_bounds_count_and_aggregate_description_size() -> None:
    base={"reviewed_sha":"a"*40,"decision":"changes_requested","dispositions":[]}
    too_many=[{"id":f"F{i}","severity":"major","description":"x"} for i in range(51)]
    assert not validate_review({**base,"findings":too_many})
    too_large=[{"id":f"F{i}","severity":"major","description":"x"*4096} for i in range(9)]
    assert not validate_review({**base,"findings":too_large})
    bounded=[{"id":f"F{i}","severity":"major","description":"x"*4096} for i in range(8)]
    assert validate_review({**base,"findings":bounded})


def test_plan_requires_exact_stage_commands_and_requirement_coverage() -> None:
    requirements = {"R1", "R2"}
    plan = {"tasks":[{"id":"1","description":"do x","paths":["src/x.py"],"test_command":["python","-m","pytest"],"requirement_ids":["R1","R2"]}],"commands":{"red":{"argv":["python","-m","pytest"],"requirement_ids":["R1","R2"]},"green":{"argv":["python","-m","pytest"],"requirement_ids":["R1","R2"]},"full":{"argv":["python","-m","pytest"],"requirement_ids":["R1","R2"]},"security":{"argv":["python","-m","compileall","src"],"requirement_ids":["R1","R2"]},"live":{"argv":["python","-m","pytest","tests/live"],"requirement_ids":["R1","R2"]}},"approved":True}
    assert validate_plan(plan, requirements)
    plan["commands"]["green"]["argv"] = ["true"]
    assert not validate_plan(plan, requirements)
