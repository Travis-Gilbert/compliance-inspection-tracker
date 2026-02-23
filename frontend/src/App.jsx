import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import ReviewQueue from "./pages/ReviewQueue";
import PropertyDetail from "./pages/PropertyDetail";
import Import from "./pages/Import";
import Export from "./pages/Export";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="/property/:id" element={<PropertyDetail />} />
        <Route path="/import" element={<Import />} />
        <Route path="/export" element={<Export />} />
      </Routes>
    </Layout>
  );
}
