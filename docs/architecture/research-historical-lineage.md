# Research Historical Lineage Map

Status: canonical historical/foundational companion to Track AD
Updated: 2026-09-21
Authority: research context and design lineage; never runtime authority

## Purpose

Frontier AI research sits on older ideas from information theory, optimization, control, databases, distributed systems, operating systems, security, formal methods, compilers, testing, human factors, and scientific measurement.

Skeleton keeps these lineages explicit for two reasons:

1. many "new AI" failure modes are older systems problems under new names;
2. a frontier method should not cause the architecture to discard stronger, older engineering invariants.

Historical inclusion is not a command to implement an old method literally. It records the conceptual invariant or failure lesson that modern work should be compared against.

## Historical lineage registry — HL001..HL110

| ID | Domain | Anchor | Lasting Skeleton relevance |
| --- | --- | --- | --- |
| HL001 | information theory | Shannon, A Mathematical Theory of Communication (1948) | entropy, coding limits, information as a measurable resource |
| HL002 | information theory | Kullback & Leibler, On Information and Sufficiency (1951) | KL divergence and distribution mismatch |
| HL003 | information theory | Cover & Thomas, Elements of Information Theory | rate-distortion, channel capacity, coding perspective |
| HL004 | learning theory | Vapnik–Chervonenkis statistical learning theory | capacity/generalization and empirical risk |
| HL005 | learning theory | Valiant, A Theory of the Learnable (1984) | PAC learnability and explicit distribution/error assumptions |
| HL006 | learning theory | Rissanen, Minimum Description Length | compression/generalization connection |
| HL007 | neural foundations | McCulloch & Pitts, A Logical Calculus of the Ideas Immanent in Nervous Activity (1943) | computational neuron abstraction |
| HL008 | neural foundations | Hebb, The Organization of Behavior (1949) | associative plasticity |
| HL009 | neural foundations | Rosenblatt, The Perceptron (1958) | learned linear decision units |
| HL010 | neural foundations | Rumelhart, Hinton & Williams, Learning Representations by Back-Propagating Errors (1986) | backpropagation as general representation-learning machinery |
| HL011 | associative memory | Hopfield, Neural Networks and Physical Systems with Emergent Collective Computational Abilities (1982) | energy-based associative memory |
| HL012 | associative memory | Kosko, Bidirectional Associative Memories (1988) | bidirectional content-addressable memory |
| HL013 | representation | Hinton & Salakhutdinov, Reducing the Dimensionality of Data with Neural Networks (2006) | learned compression/latent representation |
| HL014 | representation | Mikolov et al., Distributed Representations of Words and Phrases (2013) | distributional embedding geometry |
| HL015 | sequence models | Elman, Finding Structure in Time (1990) | recurrent state for sequence learning |
| HL016 | sequence models | Hochreiter & Schmidhuber, Long Short-Term Memory (1997) | gated recurrent memory and long dependencies |
| HL017 | sequence models | Graves et al., Connectionist Temporal Classification (2006) | alignment-free sequence objectives |
| HL018 | sequence models | Sutskever et al., Sequence to Sequence Learning with Neural Networks (2014) | encoder/decoder sequence transduction |
| HL019 | attention | Bahdanau et al., Neural Machine Translation by Jointly Learning to Align and Translate (2014) | content-dependent alignment/attention |
| HL020 | attention | Vaswani et al., Attention Is All You Need (2017) | parallel attention sequence modeling |
| HL021 | optimization | Robbins & Monro, A Stochastic Approximation Method (1951) | stochastic iterative optimization |
| HL022 | optimization | Polyak, momentum methods | inertial acceleration and optimization dynamics |
| HL023 | optimization | Nesterov accelerated gradient | first-order acceleration |
| HL024 | optimization | Duchi et al., AdaGrad (2011) | per-coordinate adaptive learning rates |
| HL025 | optimization | Tieleman & Hinton, RMSProp lecture notes | adaptive second-moment scaling |
| HL026 | optimization | Kingma & Ba, Adam (2014) | adaptive first/second-moment optimizer |
| HL027 | optimization | Loshchilov & Hutter, Decoupled Weight Decay Regularization (AdamW) | separate decay from adaptive gradient geometry |
| HL028 | optimization | Martens & Grosse, K-FAC (2015) | approximate natural-gradient curvature |
| HL029 | optimization | Gupta et al., Shampoo (2018) | tensor-structured preconditioning |
| HL030 | optimization | Smith et al., cyclical/one-cycle learning-rate work | schedule as optimization-control variable |
| HL031 | reinforcement learning | Bellman, Dynamic Programming (1957) | value recursion and optimal substructure |
| HL032 | reinforcement learning | Watkins & Dayan, Q-learning (1992) | off-policy temporal-difference control |
| HL033 | reinforcement learning | Sutton & Barto, Reinforcement Learning | TD learning, policy/value methods, eligibility traces |
| HL034 | reinforcement learning | Williams, REINFORCE (1992) | score-function policy gradients |
| HL035 | reinforcement learning | Schulman et al., Trust Region Policy Optimization (2015) | bounded policy updates |
| HL036 | reinforcement learning | Schulman et al., Proximal Policy Optimization (2017) | practical clipped policy optimization |
| HL037 | planning/search | Dijkstra, A Note on Two Problems in Connexion with Graphs (1959) | optimal shortest-path search |
| HL038 | planning/search | Hart, Nilsson & Raphael, A Formal Basis for the Heuristic Determination of Minimum Cost Paths (A*) | heuristic admissible search |
| HL039 | planning/search | Korf, Depth-first Iterative-Deepening (1985) | memory-efficient optimal search |
| HL040 | planning/search | Monte Carlo Tree Search / UCT | simulation-based tree search under uncertainty |
| HL041 | planning/control | Kalman, A New Approach to Linear Filtering and Prediction Problems (1960) | state estimation under noisy observations |
| HL042 | planning/control | Model Predictive Control literature | receding-horizon planning with feedback |
| HL043 | planning/control | Partially Observable Markov Decision Processes | belief-state planning under incomplete observations |
| HL044 | probabilistic models | Pearl, Probabilistic Reasoning in Intelligent Systems | Bayesian networks and causal graphical structure |
| HL045 | probabilistic models | Dempster–Shafer evidence theory | explicit evidence combination/uncertainty representation |
| HL046 | causality | Pearl, Causality | intervention/counterfactual distinction |
| HL047 | causality | Rubin causal model | potential-outcome treatment effects and experimental thinking |
| HL048 | retrieval/IR | Robertson & Zaragoza, BM25 probabilistic retrieval lineage | strong lexical ranking baseline |
| HL049 | retrieval/IR | Salton & McGill, vector-space information retrieval | vector similarity retrieval foundation |
| HL050 | retrieval/IR | Page et al., PageRank (1998) | graph authority via link structure |
| HL051 | retrieval/IR | Manning, Raghavan & Schütze, Introduction to Information Retrieval | evaluation, indexing, ranking foundations |
| HL052 | databases | Codd, A Relational Model of Data for Large Shared Data Banks (1970) | declarative data and schema discipline |
| HL053 | databases | Gray & Reuter, Transaction Processing | ACID, logging, recovery and concurrency control |
| HL054 | databases | Bernstein, Hadzilacos & Goodman, Concurrency Control and Recovery | serializability and recovery theory |
| HL055 | databases | Stonebraker et al., column-store/system design lineage | physical layout and workload-aware data systems |
| HL056 | distributed systems | Lamport, Time, Clocks, and the Ordering of Events in a Distributed System (1978) | logical clocks and partial ordering |
| HL057 | distributed systems | Lamport, The Part-Time Parliament / Paxos | consensus under failures |
| HL058 | distributed systems | Ongaro & Ousterhout, Raft (2014) | understandable replicated consensus |
| HL059 | distributed systems | Chandra & Toueg, Unreliable Failure Detectors | limits and structure of failure detection |
| HL060 | distributed systems | Fischer, Lynch & Paterson, Impossibility of Distributed Consensus with One Faulty Process | consensus impossibility under asynchrony |
| HL061 | distributed systems | Brewer/Gilbert-Lynch CAP theorem | consistency/availability under partition tradeoffs |
| HL062 | distributed systems | Dynamo (Amazon, 2007) | eventual consistency, vector clocks and quorum tradeoffs |
| HL063 | distributed systems | Spanner (Google, 2012) | globally distributed transactions with bounded time uncertainty |
| HL064 | distributed systems | Dean & Barroso, The Tail at Scale (2013) | tail latency as a system-level phenomenon |
| HL065 | fault tolerance | Tandem/Gray fault-tolerant systems lineage | failure detection, redundancy and recovery |
| HL066 | fault tolerance | Byzantine Generals Problem | adversarial distributed-fault model |
| HL067 | fault tolerance | Castro & Liskov, Practical Byzantine Fault Tolerance | practical replicated state under Byzantine faults |
| HL068 | operating systems | Saltzer, Reed & Clark, End-to-End Arguments in System Design (1984) | place guarantees at the layer that can truly enforce them |
| HL069 | operating systems | Lampson, Hints for Computer System Design (1983) | simplicity, caching, naming and failure-aware system design |
| HL070 | operating systems | Anderson et al., Scheduler Activations / systems scheduling lineage | resource scheduling and abstraction boundaries |
| HL071 | security | Saltzer & Schroeder, The Protection of Information in Computer Systems (1975) | least privilege, complete mediation, fail-safe defaults |
| HL072 | security | Lampson, Protection (1971) | capability/access-control foundations |
| HL073 | security | Denning, lattice model of secure information flow | information-flow control |
| HL074 | security | Bell–LaPadula model | confidentiality-oriented mandatory access control |
| HL075 | security | Biba integrity model | integrity-oriented information-flow rules |
| HL076 | security | Clark–Wilson integrity model | well-formed transactions and separation of duties |
| HL077 | cryptography | Diffie & Hellman, New Directions in Cryptography (1976) | public-key key-exchange foundations |
| HL078 | cryptography | Rivest, Shamir & Adleman, RSA (1978) | public-key signatures/encryption |
| HL079 | cryptography | Merkle trees | tamper-evident authenticated data structures |
| HL080 | formal methods | Hoare, An Axiomatic Basis for Computer Programming (1969) | program correctness logic |
| HL081 | formal methods | Dijkstra, Guarded Commands / weakest preconditions | correct-by-construction reasoning |
| HL082 | formal methods | Pnueli, temporal logic of programs | reasoning about time/liveness/safety |
| HL083 | formal methods | Clarke, Emerson & Sifakis, model checking lineage | automatic finite-state property verification |
| HL084 | formal methods | Lamport, TLA / TLA+ lineage | specification of concurrent/distributed systems |
| HL085 | formal methods | Coq / Isabelle / HOL / Lean theorem-prover lineages | machine-checked proof artifacts |
| HL086 | programming languages | Milner/Hindley type inference lineage | static type reasoning and compositional contracts |
| HL087 | programming languages | Reynolds, separation logic lineage | local reasoning about mutable state |
| HL088 | compilers | Aho, Lam, Sethi & Ullman compiler foundations | IRs, dataflow, optimization and correctness boundaries |
| HL089 | compilers | SSA form lineage | explicit data dependencies and optimization-friendly IR |
| HL090 | compilers | LLVM design lineage | portable typed IR and target-specific lowering |
| HL091 | compilers | MLIR design lineage | multi-level IR for heterogeneous systems |
| HL092 | testing | QuickCheck / property-based testing | generate broad behavioral test populations from invariants |
| HL093 | testing | Miller et al., fuzz testing lineage | randomized robustness discovery |
| HL094 | testing | American Fuzzy Lop and coverage-guided fuzzing | feedback-guided adversarial input exploration |
| HL095 | testing | differential testing lineage | cross-implementation correctness oracle |
| HL096 | software reliability | SRE error-budget literature | reliability as measurable operating constraint |
| HL097 | software reliability | chaos engineering lineage | controlled failure injection |
| HL098 | software reliability | N-version programming / recovery blocks | diverse redundancy and acceptance tests |
| HL099 | human factors | Norman, The Design of Everyday Things | affordances, feedback and human error |
| HL100 | human factors | Reason, Human Error / Swiss-cheese model | layered defenses and latent organizational failure |
| HL101 | human factors | Hollnagel, resilience engineering | adaptation under variable conditions |
| HL102 | decision science | Kahneman & Tversky, Prospect Theory | systematic human decision biases |
| HL103 | decision science | Bayesian decision theory | uncertainty + utility as decision basis |
| HL104 | scientific method | Popper, falsifiability | design claims that can lose |
| HL105 | scientific method | Fisher/Neyman–Pearson experimental statistics | hypothesis tests, power and decision errors |
| HL106 | scientific method | Box, all models are wrong / statistical modeling lineage | models are scoped approximations |
| HL107 | scientific method | Ioannidis, Why Most Published Research Findings Are False (2005) | multiple testing, bias and low prior probability |
| HL108 | scientific method | Open Science / preregistration / reproducibility movement | precommitment, artifacts and replication |
| HL109 | causal experimentation | randomized controlled experiment design | intervention beats correlation for causal claims |
| HL110 | metrology | measurement uncertainty and calibration principles | measurement instruments themselves need characterization |

## Cross-lineage conclusions

### Old systems theory constrains new agent systems

Long-running agents inherit classical problems:
- distributed ordering;
- stale authority;
- transaction commit ambiguity;
- partial failure;
- tail latency;
- retries;
- replay;
- access control;
- information-flow leakage.

A model does not make these problems disappear.

### Retrieval should keep classical baselines

Modern embedding/graph/agentic retrieval must continue to compare against lexical and probabilistic IR baselines because their cost, determinism, and failure modes are very different.

### Formal evidence has an older, stronger vocabulary than "LLM-as-judge"

Safety, liveness, invariants, refinement, model checking, theorem proving, types, and property testing remain distinct evidence classes.

### Scientific-method history is part of AI architecture

Selection bias, multiple comparisons, underpowered experiments, publication bias, instrumentation error, and irreproducibility are architecture risks once automated research can generate thousands of experiments.

### Human factors remain part of system safety

Operator overload, stale UI state, ambiguous controls, alarm fatigue, confirmation bias, and recovery under pressure are not solved by model quality.

## Mandatory historical cross-check

Before introducing a new architecture primitive, ask:

- Is this actually a known database/distributed-systems problem?
- Is there an existing security principle stronger than the proposed model behavior?
- Can a compiler/formal-method abstraction make the behavior more checkable?
- Is there a classical IR/statistical baseline that must be included?
- Does the experiment violate known scientific-measurement principles?
- Does the design assume perfect humans/operators?

## Historical evidence maturity

Historical work can be foundational while still being scoped.

Examples:

- CAP does not mean every distributed system "chooses two" in a simplistic way.
- FLP is an impossibility result under a specific asynchronous/failure model, not a ban on practical consensus.
- ACID does not imply one database isolation choice fits every state plane.
- formal proof does not prove that the formal specification matches user intent.
- least privilege does not automatically define the right capability granularity.

Skeleton stores the actual theorem/assumptions, not slogans.

## Planning checkpoint

~~~text
checkpoint_id: PLAN-20260921-HISTORICAL-RESEARCH-LINEAGE
created_at: 2026-09-21
historical_anchors: HL001..HL110
production_authority_granted: false
purpose: prevent frontier AI research from forgetting mature systems/science foundations
~~~
