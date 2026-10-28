"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useUsersDeleteMe } from "@/lib/api/generated/users/users";
import { errorMessage } from "@/lib/forms";

const WORD = "DELETE";

export function DangerZone() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const remove = useUsersDeleteMe();
  const [typed, setTyped] = useState("");

  return (
    <Card className="border-destructive/40 max-w-2xl">
      <CardHeader>
        <CardTitle className="text-base">Your data</CardTitle>
        <CardDescription>Download everything, or delete your account for good.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 text-sm">
        <div className="grid gap-2">
          <p className="text-muted-foreground">
            A zip with your profile, resumes (the original files), preferences, jobs, match scores,
            applications, drafts and history. Passwords and access tokens are never included.
          </p>
          <Button asChild variant="outline" className="justify-self-start">
            {/* A plain link: the browser downloads the zip with your session cookie. */}
            <a href="/api/v1/users/me/export" download>
              <Download className="size-4" /> Export my data
            </a>
          </Button>
        </div>

        <div className="grid gap-2">
          <p className="text-muted-foreground">
            Deleting signs you out everywhere, disconnects Gmail and Google Sheets, and erases your
            resumes, profile, applications and history. The tracker spreadsheet stays in your own
            Google Drive. This can&apos;t be undone.
          </p>
          <AlertDialog onOpenChange={() => setTyped("")}>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" className="justify-self-start">
                <Trash2 className="size-4" /> Delete my account
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete your account?</AlertDialogTitle>
                <AlertDialogDescription>
                  Everything you stored in JobPilot is erased within the hour and can&apos;t be
                  recovered. Export your data first if you want a copy.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div className="grid gap-1.5">
                <Label htmlFor="confirm-delete">
                  Type <strong>{WORD}</strong> to confirm
                </Label>
                <Input
                  id="confirm-delete"
                  autoComplete="off"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                />
              </div>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep my account</AlertDialogCancel>
                <Button
                  variant="destructive"
                  disabled={typed !== WORD || remove.isPending}
                  onClick={() =>
                    remove.mutate(
                      { data: { confirm: typed } },
                      {
                        onSuccess: () => {
                          queryClient.clear();
                          toast("Your account was deleted.");
                          router.replace("/login");
                        },
                        onError: (e) => toast.error(errorMessage(e)),
                      },
                    )
                  }
                >
                  {remove.isPending ? "Deleting…" : "Delete forever"}
                </Button>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </CardContent>
    </Card>
  );
}
