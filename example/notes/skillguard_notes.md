# Notes: Reachability-based Capability Confinement for LLM Agents under Indirect Prompt Injection

- Given sound skill summaries and policies, SkillGuard represents security-relevant transitions with a Skill Impact Graph, specifies admissible control over skill parameters through steerability signatures, and mediates invocations with an inline reference monitor.
- Skill Impact Graph, initial capability set, and a forbidden state B.
- Graph-based formulations enable such transitions to be analyzed through reachability and allow unsafe paths to be disconnected using minimum-cut techniques. SkillGuard adopts this formulation to model agent execution, where nodes represent security-relevant states and skill invocations induce transitions between them.
- **Steerability Signatures**:
    - Determining whether such influence is safe from the natural-language semantics of argument is unreliable. Instead, SkillGuard defines explicit constraints for each skill parameter. Under these constraints, the steerability signature specifies the type and permitted value range of each parameter.
- **Capability Restriction Mechanism**:
    - SkillGuard recomputes capability restrictions upon state contamination, disconnecting all paths to forbidden states on the execution graph at a minimal cost. When a contamination event is committed, SkillGuard evaluates the reachability from the current state q to the forbidden set B.
