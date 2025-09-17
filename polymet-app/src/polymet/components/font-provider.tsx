import React from "react";

export default function FontProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap"
      />

      <style jsx global>{`
        html {
          font-family: "Roboto", sans-serif;
        }
        body {
          font-family: "Roboto", sans-serif;
        }
      `}</style>
      {children}
    </>
  );
}
