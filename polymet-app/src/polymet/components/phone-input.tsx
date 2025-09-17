import React, { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface PhoneInputProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
  error?: string;
}

export function PhoneInput({
  value,
  onChange,
  className,
  error,
}: PhoneInputProps) {
  const [focused, setFocused] = useState(false);

  const formatPhoneNumber = (input: string) => {
    // Remove all non-digit characters
    const digits = input.replace(/\D/g, "");

    // Format the phone number as (XXX) XXX-XXXX
    if (digits.length <= 3) {
      return digits;
    } else if (digits.length <= 6) {
      return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    } else {
      return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatPhoneNumber(e.target.value);
    onChange(formatted);
  };

  return (
    <div className={cn("space-y-2", className)}>
      <Label
        htmlFor="phone"
        className={cn(
          "text-sm font-medium transition-colors",
          focused ? "text-primary" : "text-foreground"
        )}
      >
        Phone Number
      </Label>
      <Input
        id="phone"
        type="tel"
        value={value}
        onChange={handleChange}
        placeholder="(555) 123-4567"
        className={cn("transition-all", error ? "border-destructive" : "")}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        maxLength={14} // (XXX) XXX-XXXX
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}

export default PhoneInput;
