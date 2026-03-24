import { useState } from "react";
import { supabase } from "../supabase";

export default function EmailSignup() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | loading | success | error

  async function handleSubmit(e) {
    e.preventDefault();
    if (!email || !email.includes("@")) return;

    setState("loading");
    try {
      const { error } = await supabase
        .from("subscribers")
        .insert({ email, source: "main_site" });

      if (error && error.code === "23505") {
        // Duplicate email — still treat as success
        setState("success");
        return;
      }
      if (error) throw error;
      setState("success");
    } catch (err) {
      console.error(err);
      setState("error");
    }
  }

  return (
    <section className="signup-section">
      <div className="signup-inner">
        <div className="signup-badge">
          <span className="badge-dot" />
          GET ALERTS
        </div>
        <h2 className="signup-headline">
          Never miss a <span className="signup-highlight">sell-out</span>
        </h2>
        <p className="signup-sub">
          We'll email you the moment a toy hits Critical stock or a resale spike
          is detected. Free. No spam.
        </p>

        {state === "success" ? (
          <div className="signup-success">
            🎯 You're on the list — you'll know first!
          </div>
        ) : (
          <form className="signup-form" onSubmit={handleSubmit}>
            <input
              type="email"
              className="signup-input"
              placeholder="your@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={state === "loading"}
            />
            <button
              type="submit"
              className="signup-btn"
              disabled={state === "loading"}
            >
              {state === "loading" ? "..." : "Get Alerts →"}
            </button>
          </form>
        )}
        {state === "error" && (
          <p className="signup-error">Something went wrong. Try again.</p>
        )}
      </div>
    </section>
  );
}
