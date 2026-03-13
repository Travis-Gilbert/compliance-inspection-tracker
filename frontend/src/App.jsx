import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import Dashboard from "./pages/Dashboard";
import ReviewQueue from "./pages/ReviewQueue";
import PropertyDetail from "./pages/PropertyDetail";
import Import from "./pages/Import";
import Export from "./pages/Export";
import LeadershipMap from "./pages/LeadershipMap";

function PageBoundary({ children }) {
  return <ErrorBoundary>{children}</ErrorBoundary>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/map" element={<PageBoundary><LeadershipMap /></PageBoundary>} />
      <Route element={<Layout />}>
        <Route path="/" element={<PageBoundary><Dashboard /></PageBoundary>} />
        <Route path="/review" element={<PageBoundary><ReviewQueue /></PageBoundary>} />
        <Route path="/property/:id" element={<PageBoundary><PropertyDetail /></PageBoundary>} />
        <Route path="/import" element={<PageBoundary><Import /></PageBoundary>} />
        <Route path="/export" element={<PageBoundary><Export /></PageBoundary>} />
      </Route>
    </Routes>
  );
}
