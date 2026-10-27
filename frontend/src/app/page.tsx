import { redirect } from "next/navigation";

export default function Home() {
  // The route guard sends signed-out visitors on to /login.
  redirect("/jobs");
}
