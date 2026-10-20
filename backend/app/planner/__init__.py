"""The meal planner (Phase 5, D-028/D-029): budget and group requests with guaranteed-correct plans.

The LLM extracts a MealRequest (request.py); code finds the candidate dishes (candidates.py), builds combinations
(build.py), checks every hard rule with an independent checker (rules.py), scores and diversifies (score.py), and
answers impossible requests honestly (plan.py).
"""
