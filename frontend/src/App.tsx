import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/ui";

function App() {
  return (
    <ToastProvider>
      <AppShell />
    </ToastProvider>
  );
}

export default App;
