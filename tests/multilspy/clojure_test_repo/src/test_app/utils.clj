(ns test-app.utils
  (:require [test-app.core :as core]))

(defn calculate-area
  "Calculates the area of a rectangle"
  [width height]
  (core/multiply width height))

(defn format-greeting
  "Formats a greeting message"
  [name]
  (str "Welcome, " (core/greet name)))

(defn sum-list
  "Sums a list of numbers"
  [numbers]
  (reduce core/add 0 numbers))
