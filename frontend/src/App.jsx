import Protected from "./components/Protected"
import Public from "./components/Public"
import useAuth from "./hooks/useAuth"
export default function App() {
  const { isLogin } = useAuth()
  console.log(isLogin)
  return (
    <div>
      {isLogin ? <Protected /> : <Public />}
    </div>
  )
}