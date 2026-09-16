import { BrowserRouter, Routes, Route } from "react-router-dom";
import Overview from "./Overview";
import TopicDetail from "./TopicDetail";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/topics/:id" element={<TopicDetail />} />
      </Routes>
    </BrowserRouter>
  );
}
