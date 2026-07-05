import './GradientText.css';

type GradientTextProps = {
    children: React.ReactNode;
    className?: string;
    colors?: string[];
    animationSpeed?: number;
    showBorder?: boolean;
};

export default function GradientText({
    children,
    className = '',
    colors = ['#5b57ce', '#40ffaa', '#5b57ce', '#40ffaa', '#5b57ce'],
    animationSpeed = 8,
    showBorder = false
}: GradientTextProps) {
    const gradientStyle = {
        backgroundImage: `linear-gradient(to right, ${colors.join(', ')})`,
        animationDuration: `${animationSpeed}s`
    };

    return (
        <div className={`animated-gradient-text ${className}`}>
            {showBorder && <div className="gradient-overlay" style={gradientStyle}></div>}
            <div className="text-content" style={gradientStyle}>
                {children}
            </div>
        </div>
    );
}
