import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import useStore from "./store/useStore";
import Login from "./components/Login";
import Layout from "./components/Layout";
import ChatPanel from "./components/ChatPanel";

function ProtectedRoute({ children }) {
  const isAuthenticated = useStore((s) => s.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function PublicRoute({ children }) {
  const isAuthenticated = useStore((s) => s.isAuthenticated);
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={
            <PublicRoute>
              <Login />
            </PublicRoute>
          }
        />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<ChatPanel />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
