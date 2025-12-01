---
default_provider:                  # Uses project default from configs/config.yaml
default_model:                     # Uses provider's built-in default
max_parallel: 4
base_file: base_notebook.ipynb
assignment_type: structured
total_marks: 100
---

# Lab 2: Decision Trees

## Assignment Overview

This lab introduces students to Decision Tree classifiers using the scikit-learn library. Students will work with the Breast Cancer Wisconsin (Diagnostic) dataset to build, train, and evaluate decision tree models.

## Learning Objectives

By completing this lab, students will:
1. Understand how to implement decision tree classifiers in Python
2. Learn to split data into training and validation sets
3. Practice model instantiation, training, and prediction
4. Evaluate model performance using accuracy metrics and classification reports
5. Understand the impact of feature scaling on different algorithms

## Assignment Structure

This is a fill-in-the-blank structured assignment with 7 activities:

### Activity 1: Data Splitting
Students split the dataset into training and validation sets using sklearn's train_test_split.

### Activity 2: Model Instantiation
Students create a DecisionTreeClassifier instance.

### Activity 3: Model Training
Students fit the decision tree to training data.

### Activity 4: Prediction
Students use the trained model to make predictions on validation data.

### Activity 5: Model Evaluation
Students evaluate performance using accuracy_score() and classification_report().

### Activity 6: Feature Scaling Experiment
Students normalize data using StandardScaler and compare performance.

### Activity 7: Analysis Question
Students explain whether feature scaling is necessary for decision trees based on their experimental results.

## Prerequisites

Students should have completed Lab 1 (k-NN classifier) and be familiar with:
- Basic Python programming
- NumPy and pandas libraries
- Basic machine learning concepts (training/validation split, model fitting)

## Grading Criteria

Total: 100 points

- Correctness (60 points): Code executes without errors and produces correct results
- Code Quality (20 points): Proper use of sklearn functions, appropriate variable names, clean code
- Understanding (20 points): Demonstrates comprehension through correct implementation and clear explanation in Activity 7

## Notes

- Students must use the exact variable names specified in the instructions
- Students may add additional cells for exploration, but must not modify cells outside the designated input areas
- The assignment uses the built-in sklearn Breast Cancer dataset (no external files needed)
