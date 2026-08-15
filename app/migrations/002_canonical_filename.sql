-- Adds explicit canonical filename storage for standalone Java exercise
-- tasks, so the file path used by VS Code / the compiler / Git is never
-- re-derived from display title text at runtime (see curriculum/build_schedule.py
-- EXERCISE_FILENAMES for why naive PascalCase inference is wrong for some
-- titles, e.g. "Maximum of 3" -> "MaximumOf3" instead of "MaximumOfThree").
ALTER TABLE tasks ADD COLUMN canonical_filename TEXT;
