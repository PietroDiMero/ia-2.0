"use client"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { ReactNode } from "react"

export function Dialog({ children }: { children: ReactNode }) {
  return <DialogPrimitive.Root>{children}</DialogPrimitive.Root>
}

export const DialogTrigger = DialogPrimitive.Trigger

export function DialogContent({ children }: { children: ReactNode }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 bg-black/30" />
      <DialogPrimitive.Content className="fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[90vw] max-w-lg rounded-lg border bg-white dark:bg-neutral-900 p-4 shadow-lg">
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export const DialogTitle = DialogPrimitive.Title
export const DialogDescription = DialogPrimitive.Description
export const DialogClose = DialogPrimitive.Close
