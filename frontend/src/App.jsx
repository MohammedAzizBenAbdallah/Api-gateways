import Protected from "./components/Protected";
import Public from "./components/Public";
import useAuth from "./hooks/useAuth";
import "./index.css";
export default function App() {
  const { isLogin } = useAuth();
  return <div>{isLogin ? <Protected /> : <Public />}</div>;
}
