import { ArrowLeft, MapPinOff } from "lucide-react";
import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/States";

export default function NotFound() {
  return (
    <div className="pt-10">
      <h1 className="sr-only">Page not found</h1>
      <EmptyState icon={MapPinOff} title="Page not found" description="The page you asked for doesn't exist." action={<ButtonLink to="/" icon={ArrowLeft}>Back to overview</ButtonLink>} />
    </div>
  );
}
