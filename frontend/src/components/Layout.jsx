import { Outlet } from "react-router-dom";
import useStore from "../store/useStore";
import DocumentPanel from "./DocumentPanel";

export default function Layout() {
  const logout = useStore((s) => s.logout);

  return (
    <div className="flex h-screen flex-col bg-gray-100">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b bg-white px-6 py-3 shadow-sm">
        <h1 className="text-lg font-bold text-gray-800">FitCoach AI</h1>
        <button
          onClick={logout}
          className="rounded-md px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-800"
        >
          退出登录
        </button>
      </header>

      <main className="flex flex-1 overflow-hidden">
        <DocumentPanel />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
