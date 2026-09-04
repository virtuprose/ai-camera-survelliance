import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap border text-sm font-semibold tracking-[-0.01em] outline-none transition-[background-color,border-color,color,box-shadow,filter,transform] duration-200 ease-out focus-visible:ring-[3px] focus-visible:ring-ring/25 disabled:pointer-events-none disabled:opacity-45 active:scale-[0.97] motion-reduce:transition-none motion-reduce:active:scale-100 aria-invalid:border-destructive aria-invalid:ring-destructive/20 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/18%),0_1px_2px_rgb(0_0_0/10%)] hover:brightness-[1.06] hover:shadow-[inset_0_1px_0_rgb(255_255_255/20%),0_2px_5px_rgb(0_102_204/16%)]",
        destructive:
          "border-destructive bg-destructive text-white shadow-[inset_0_1px_0_rgb(255_255_255/16%),0_1px_2px_rgb(0_0_0/10%)] hover:brightness-[1.04] focus-visible:ring-destructive/20",
        outline:
          "border-border bg-card text-foreground shadow-[inset_0_1px_0_rgb(255_255_255/85%),0_1px_2px_rgb(0_0_0/5%)] hover:border-input hover:bg-muted/70",
        secondary:
          "border-border/70 bg-secondary text-secondary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/70%)] hover:bg-secondary/75",
        ghost:
          "border-transparent bg-transparent text-foreground shadow-none hover:bg-muted",
        link: "border-transparent bg-transparent p-0 text-primary shadow-none underline-offset-4 hover:underline",
        soft:
          "border-primary/15 bg-primary text-primary-foreground shadow-[inset_0_1px_0_rgb(255_255_255/20%),0_4px_12px_rgb(0_102_204/18%)] hover:brightness-[1.06] hover:shadow-[inset_0_1px_0_rgb(255_255_255/24%),0_6px_16px_rgb(0_102_204/22%)]",
      },
      size: {
        default: "h-10 rounded-[10px] px-4 py-2 has-[>svg]:px-3.5",
        xs: "h-7 gap-1 rounded-[7px] px-2.5 text-xs has-[>svg]:px-2 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-9 gap-1.5 rounded-[9px] px-3.5 has-[>svg]:px-3",
        lg: "h-11 rounded-[11px] px-6 has-[>svg]:px-5",
        icon: "size-10 rounded-[10px]",
        "icon-xs": "size-7 rounded-[7px] [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-9 rounded-[9px]",
        "icon-lg": "size-11 rounded-[11px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
