import { useState, useEffect } from "react";
import { supabase } from "./supabase";
import ToyCard from "./components/ToyCard";
import Ticker from "./components/Ticker";
import HeroSection from "./components/HeroSection";
import FilterBar from "./components/FilterBar";
import PredictionsSection from "./components/PredictionsSection";
import EmailSignup from "./components/EmailSignup";

export default function App() {
  const [toys, setToys] = useState([]);
  const [content, setContent] = useState({});
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    try {
      const [scoresRes, contentRes] = await Promise.all([
        supabase.from("toy_scores").select("*").order("heat_score", { ascending: false }),
        supabase.from("toy_content").select("*"),
      ]);

      if (scoresRes.data) setToys(scoresRes.data);
      if (contentRes.data) {
        const map = {};
        contentRes.data.forEach((c) => (map[c.toy_id] = c));
        setContent(map);
      }
    } catch (err) {
      console.error("Failed to fetch data:", err);
    } finally {
      setLoading(false);
    }
  }

  const categories = ["all", ...new Set(toys.map((t) => t.category).filter(Boolean))];

  const filtered =
    filter === "all"
      ? toys
      : toys.filter((t) => t.category === filter);

  const trending = filtered.filter((t) => t.status === "Peak Demand");
  const rising = filtered.filter((t) => t.status === "Rising Fast");
  const emerging = filtered.filter((t) => t.breakout_flag);

  return (
    <div className="app">
      <Ticker toys={toys} content={content} />
      <HeroSection />
      <main className="main">
        <FilterBar categories={categories} active={filter} onChange={setFilter} />

        {loading ? (
          <div className="loading-state">
            <div className="loading-dots">
              <span /><span /><span />
            </div>
            <p>Scanning signals...</p>
          </div>
        ) : (
          <>
            {trending.length > 0 && (
              <Section title="🔥 Peak Demand" subtitle="Selling out now — act fast" toys={trending} content={content} />
            )}
            {rising.length > 0 && (
              <Section title="📈 Rising Fast" subtitle="Momentum building — get ahead" toys={rising} content={content} />
            )}
            {emerging.length > 0 && (
              <Section title="🌱 On Our Radar" subtitle="Our model says these break out soon" toys={emerging} content={content} prediction />
            )}
            <EmailSignup />
          </>
        )}
      </main>
    </div>
  );
}

function Section({ title, subtitle, toys, content, prediction = false }) {
  return (
    <section className="toy-section">
      <div className="section-header">
        <h2 className="section-title">{title}</h2>
        <p className="section-subtitle">{subtitle}</p>
      </div>
      <div className="toy-grid">
        {toys.map((toy) => (
          <ToyCard
            key={toy.toy_id}
            toy={toy}
            content={content[toy.toy_id]}
            showPrediction={prediction}
          />
        ))}
      </div>
    </section>
  );
}
