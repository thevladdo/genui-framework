/**
 * ButtonsComponent
 * Animated button component with multiple variants
 */

import React from "react";
import type { ButtonsComponentData, ButtonDef, ButtonVariant } from "../types";

export interface ButtonsComponentProps {
  data: ButtonsComponentData;
  className?: string;
}

interface SingleButtonProps {
  button: ButtonDef;
}

const ArrowIcon: React.FC<{ direction: "left" | "right" }> = ({
  direction,
}) => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ transform: direction === "left" ? "rotate(180deg)" : "none" }}
  >
    <path d="M5 12h14" />
    <path d="m12 5 7 7-7 7" />
  </svg>
);

const SingleButton: React.FC<SingleButtonProps> = ({ button }) => {
  const {
    label,
    url,
    onClick,
    style = "primary",
    showArrow,
    arrowPlacement = "right",
    borderRadius,
    backgroundColor,
    textColor,
    disabled = false,
    size = "md",
  } = button;

  // Arrow shows by default on all buttons, unless explicitly set to false
  const shouldShowArrow = showArrow !== false;

  const classes = [
    "genui-button",
    `genui-button--${style}`,
    `genui-button--${size}`,
    shouldShowArrow && "genui-button--with-arrow",
    disabled && "genui-button--disabled",
  ]
    .filter(Boolean)
    .join(" ");

  const customStyle: React.CSSProperties = {};
  if (borderRadius) customStyle.borderRadius = borderRadius;
  if (backgroundColor) customStyle.backgroundColor = backgroundColor;
  if (textColor) customStyle.color = textColor;

  const handleClick = (e: React.MouseEvent) => {
    if (disabled) return;

    if (onClick) {
      e.preventDefault();
      onClick();
    }
  };

  const content = (
    <>
      {shouldShowArrow && arrowPlacement === "left" && (
        <span className="genui-button__arrow genui-button__arrow--left">
          <ArrowIcon direction="left" />
        </span>
      )}
      <span className="genui-button__label">{label}</span>
      {shouldShowArrow && arrowPlacement === "right" && (
        <span className="genui-button__arrow genui-button__arrow--right">
          <ArrowIcon direction="right" />
        </span>
      )}
    </>
  );

  if (url && !onClick) {
    return (
      <a
        href={url}
        className={classes}
        target="_blank"
        rel="noopener noreferrer"
        aria-disabled={disabled}
        style={Object.keys(customStyle).length > 0 ? customStyle : undefined}
      >
        {content}
      </a>
    );
  }

  return (
    <button
      className={classes}
      onClick={handleClick}
      disabled={disabled}
      type="button"
      style={Object.keys(customStyle).length > 0 ? customStyle : undefined}
    >
      {content}
    </button>
  );
};

export const ButtonsComponent: React.FC<ButtonsComponentProps> = ({
  data,
  className = "",
}) => {
  const { buttons, direction = "horizontal", align = "start", gap } = data;

  const containerClass = [
    "genui-buttons",
    `genui-buttons--${direction}`,
    `genui-buttons--${align}`,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const containerStyle: React.CSSProperties = gap ? { gap: `${gap}px` } : {};

  return (
    <div className={containerClass} style={containerStyle}>
      {buttons.map((button, index) => (
        <SingleButton key={`${button.label}-${index}`} button={button} />
      ))}
    </div>
  );
};

export default ButtonsComponent;
