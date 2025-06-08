(ns test-app.core)

(defn greet
  "A simple greeting function"
  [name]
  (str "Hello, " name "!"))

(defn add
  "Adds two numbers"
  [a b]
  (+ a b))

(defn multiply
  "Multiplies two numbers"
  [a b]
  (* a b))

(defn -main
  "Main entry point"
  [& args]
  (println (greet "World"))
  (println "2 + 3 =" (add 2 3))
  (println "4 * 5 =" (multiply 4 5)))
