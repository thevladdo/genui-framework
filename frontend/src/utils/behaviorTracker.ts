/**
 * BehaviorTracker
 * Collects user behavior data for analysis by the BehaveAgent
 */

export interface ClickEvent {
  x: number;
  y: number;
  target: string;
  targetId?: string;
  targetClass?: string;
  timestamp: number;
  viewportWidth: number;
  viewportHeight: number;
}

export interface ScrollEvent {
  scrollY: number;
  scrollDepthPercent: number;
  direction: 'up' | 'down';
  timestamp: number;
}

export interface PageVisit {
  path: string;
  title: string;
  enterTime: number;
  exitTime?: number;
  duration?: number;
  referrer?: string;
}

export interface HoverEvent {
  target: string;
  targetId?: string;
  duration: number;
  timestamp: number;
}

export interface ElementInteraction {
  elementId: string;
  elementType: string;
  interactionType: 'click' | 'hover' | 'focus' | 'scroll-into-view';
  timestamp: number;
  metadata?: Record<string, unknown>;
}

export interface BehaviorRecord {
  sessionId: string;
  userId: string;
  startTime: number;
  lastActivity: number;
  clicks: ClickEvent[];
  scrollEvents: ScrollEvent[];
  pageVisits: PageVisit[];
  hoverEvents: HoverEvent[];
  elementInteractions: ElementInteraction[];
  // Aggregated metrics
  metrics: {
    totalClicks: number;
    totalScrollDistance: number;
    maxScrollDepth: number;
    averageTimePerPage: number;
    mostClickedAreas: Array<{ zone: string; count: number }>;
    navigationPattern: string[];
  };
}

export interface BehaviorTrackerOptions {
  sessionId: string;
  userId: string;
  trackClicks?: boolean;
  trackScroll?: boolean;
  trackPageVisits?: boolean;
  trackHover?: boolean;
  hoverThreshold?: number; // ms before hover is recorded
  scrollDebounce?: number; // ms debounce for scroll events
  maxEventsPerType?: number; // prevent memory issues
  enableHeatmapZones?: boolean;
}

type HeatmapZone = 'top-left' | 'top-center' | 'top-right' | 
                   'middle-left' | 'middle-center' | 'middle-right' |
                   'bottom-left' | 'bottom-center' | 'bottom-right';

const DEFAULT_OPTIONS: Partial<BehaviorTrackerOptions> = {
  trackClicks: true,
  trackScroll: true,
  trackPageVisits: true,
  trackHover: true,
  hoverThreshold: 500,
  scrollDebounce: 150,
  maxEventsPerType: 100,
  enableHeatmapZones: true,
};

export class BehaviorTracker {
  private options: BehaviorTrackerOptions;
  private record: BehaviorRecord;
  private isTracking: boolean = false;
  private clickHandler: ((e: MouseEvent) => void) | null = null;
  private scrollHandler: (() => void) | null = null;
  private hoverHandler: ((e: MouseEvent) => void) | null = null;
  private mouseOutHandler: ((e: MouseEvent) => void) | null = null;
  private visibilityHandler: (() => void) | null = null;
  
  // Tracking state
  private lastScrollY: number = 0;
  private scrollTimeout: ReturnType<typeof setTimeout> | null = null;
  private hoverTarget: EventTarget | null = null;
  private hoverStartTime: number = 0;
  private currentPage: PageVisit | null = null;

  constructor(options: BehaviorTrackerOptions) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.record = this.createEmptyRecord();
  }

  private createEmptyRecord(): BehaviorRecord {
    return {
      sessionId: this.options.sessionId,
      userId: this.options.userId,
      startTime: Date.now(),
      lastActivity: Date.now(),
      clicks: [],
      scrollEvents: [],
      pageVisits: [],
      hoverEvents: [],
      elementInteractions: [],
      metrics: {
        totalClicks: 0,
        totalScrollDistance: 0,
        maxScrollDepth: 0,
        averageTimePerPage: 0,
        mostClickedAreas: [],
        navigationPattern: [],
      },
    };
  }

  /**
   * Start tracking user behavior
   */
  start(): void {
    if (this.isTracking) return;
    
    this.isTracking = true;
    this.record.startTime = Date.now();
    
    // Track clicks
    if (this.options.trackClicks) {
      this.clickHandler = this.handleClick.bind(this);
      document.addEventListener('click', this.clickHandler, { passive: true });
    }
    
    // Track scroll
    if (this.options.trackScroll) {
      this.scrollHandler = this.handleScroll.bind(this);
      window.addEventListener('scroll', this.scrollHandler, { passive: true });
    }
    
    // Track hover
    if (this.options.trackHover) {
      this.hoverHandler = this.handleMouseOver.bind(this);
      this.mouseOutHandler = this.handleMouseOut.bind(this);
      document.addEventListener('mouseover', this.hoverHandler, { passive: true });
      document.addEventListener('mouseout', this.mouseOutHandler, { passive: true });
    }
    
    // Track page visibility changes
    this.visibilityHandler = this.handleVisibilityChange.bind(this);
    document.addEventListener('visibilitychange', this.visibilityHandler);
    
    // Initialize page visit tracking
    if (this.options.trackPageVisits) {
      this.trackPageEnter();
    }
  }

  /**
   * Stop tracking and cleanup
   */
  stop(): void {
    if (!this.isTracking) return;
    
    this.isTracking = false;
    
    // Complete current page visit
    if (this.currentPage) {
      this.completePageVisit();
    }

    if (this.clickHandler) {
      document.removeEventListener('click', this.clickHandler);
    }
    if (this.scrollHandler) {
      window.removeEventListener('scroll', this.scrollHandler);
    }
    if (this.hoverHandler) {
      document.removeEventListener('mouseover', this.hoverHandler);
    }
    if (this.mouseOutHandler) {
      document.removeEventListener('mouseout', this.mouseOutHandler);
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
    }
    
    if (this.scrollTimeout) {
      clearTimeout(this.scrollTimeout);
    }
  }

  /**
   * Get current behavior record for sending to backend
   */
  getRecord(): BehaviorRecord {
    this.updateMetrics();
    return { ...this.record };
  }

  /**
   * Get a compact summary suitable for API calls
   */
  getCompactSummary(): {
    sessionId: string;
    userId: string;
    duration: number;
    clickCount: number;
    maxScrollDepth: number;
    pagesVisited: number;
    recentClicks: ClickEvent[];
    recentInteractions: ElementInteraction[];
    heatmapZones: Array<{ zone: string; count: number }>;
    navigationPath: string[];
  } {
    this.updateMetrics();
    
    return {
      sessionId: this.record.sessionId,
      userId: this.record.userId,
      duration: Date.now() - this.record.startTime,
      clickCount: this.record.metrics.totalClicks,
      maxScrollDepth: this.record.metrics.maxScrollDepth,
      pagesVisited: this.record.pageVisits.length,
      recentClicks: this.record.clicks.slice(-10),
      recentInteractions: this.record.elementInteractions.slice(-20),
      heatmapZones: this.record.metrics.mostClickedAreas,
      navigationPath: this.record.metrics.navigationPattern.slice(-10),
    };
  }

  /**
   * Reset the behavior record
   */
  reset(): void {
    const currentPageBackup = this.currentPage;
    this.record = this.createEmptyRecord();
    this.currentPage = currentPageBackup;
  }

  /**
   * Track a custom element interaction
   */
  trackInteraction(
    elementId: string, 
    elementType: string, 
    interactionType: ElementInteraction['interactionType'],
    metadata?: Record<string, unknown>
  ): void {
    this.addElementInteraction({
      elementId,
      elementType,
      interactionType,
      timestamp: Date.now(),
      metadata,
    });
  }

  /**
   * Track navigation to a new page/route
   */
  trackNavigation(path: string, title?: string): void {
    if (this.currentPage) {
      this.completePageVisit();
    }
    this.trackPageEnter(path, title);
  }




  // Private handlers

  private handleClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    
    const clickEvent: ClickEvent = {
      x: e.clientX,
      y: e.clientY,
      target: target.tagName.toLowerCase(),
      targetId: target.id || undefined,
      targetClass: target.className || undefined,
      timestamp: Date.now(),
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
    
    this.addClick(clickEvent);
    this.record.lastActivity = Date.now();
    
    // Track as element interaction if it has an ID or data attribute
    if (target.id || target.dataset.trackId) {
      this.addElementInteraction({
        elementId: target.id || target.dataset.trackId || target.tagName,
        elementType: target.tagName.toLowerCase(),
        interactionType: 'click',
        timestamp: Date.now(),
        metadata: {
          text: target.textContent?.slice(0, 50),
          href: (target as HTMLAnchorElement).href,
        },
      });
    }
  }

  private handleScroll(): void {
    if (this.scrollTimeout) {
      clearTimeout(this.scrollTimeout);
    }
    
    this.scrollTimeout = setTimeout(() => {
      const scrollY = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const scrollDepthPercent = docHeight > 0 ? (scrollY / docHeight) * 100 : 0;
      
      const scrollEvent: ScrollEvent = {
        scrollY,
        scrollDepthPercent: Math.round(scrollDepthPercent),
        direction: scrollY > this.lastScrollY ? 'down' : 'up',
        timestamp: Date.now(),
      };
      
      this.addScrollEvent(scrollEvent);
      this.lastScrollY = scrollY;
      this.record.lastActivity = Date.now();
    }, this.options.scrollDebounce);
  }

  private handleMouseOver(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    
    // Only track hover on significant elements
    if (!this.isSignificantElement(target)) return;
    
    this.hoverTarget = target;
    this.hoverStartTime = Date.now();
  }

  private handleMouseOut(e: MouseEvent): void {
    if (!this.hoverTarget || e.target !== this.hoverTarget) return;
    
    const duration = Date.now() - this.hoverStartTime;
    
    if (duration >= (this.options.hoverThreshold || 500)) {
      const target = this.hoverTarget as HTMLElement;
      
      const hoverEvent: HoverEvent = {
        target: target.tagName.toLowerCase(),
        targetId: target.id || undefined,
        duration,
        timestamp: this.hoverStartTime,
      };
      
      this.addHoverEvent(hoverEvent);
    }
    
    this.hoverTarget = null;
    this.hoverStartTime = 0;
  }

  private handleVisibilityChange(): void {
    if (document.hidden && this.currentPage) {
      this.completePageVisit();
    } else if (!document.hidden && this.options.trackPageVisits) {
      this.trackPageEnter();
    }
  }

  private isSignificantElement(el: HTMLElement): boolean {
    const significantTags = ['a', 'button', 'input', 'select', 'img', 'video'];
    const hasInteractiveRole = el.getAttribute('role') === 'button' || el.getAttribute('role') === 'link';
    const hasDataTrack = !!el.dataset.trackId;
    
    return significantTags.includes(el.tagName.toLowerCase()) || hasInteractiveRole || hasDataTrack || !!el.id;
  }

  private trackPageEnter(path?: string, title?: string): void {
    this.currentPage = {
      path: path || window.location.pathname,
      title: title || document.title,
      enterTime: Date.now(),
      referrer: document.referrer || undefined,
    };
    
    this.record.metrics.navigationPattern.push(this.currentPage.path);
  }

  private completePageVisit(): void {
    if (!this.currentPage) return;
    
    this.currentPage.exitTime = Date.now();
    this.currentPage.duration = this.currentPage.exitTime - this.currentPage.enterTime;
    
    this.addPageVisit(this.currentPage);
    this.currentPage = null;
  }



  // Data management with limits

  private addClick(click: ClickEvent): void {
    if (this.record.clicks.length >= (this.options.maxEventsPerType || 100)) {
      this.record.clicks.shift();
    }
    this.record.clicks.push(click);
    this.record.metrics.totalClicks++;
    
    // Update heatmap zones
    if (this.options.enableHeatmapZones) {
      this.updateHeatmapZone(click);
    }
  }

  private addScrollEvent(event: ScrollEvent): void {
    if (this.record.scrollEvents.length >= (this.options.maxEventsPerType || 100)) {
      this.record.scrollEvents.shift();
    }
    this.record.scrollEvents.push(event);
    
    // Update metrics
    if (event.scrollDepthPercent > this.record.metrics.maxScrollDepth) {
      this.record.metrics.maxScrollDepth = event.scrollDepthPercent;
    }
  }

  private addPageVisit(visit: PageVisit): void {
    if (this.record.pageVisits.length >= (this.options.maxEventsPerType || 100)) {
      this.record.pageVisits.shift();
    }
    this.record.pageVisits.push(visit);
  }

  private addHoverEvent(event: HoverEvent): void {
    if (this.record.hoverEvents.length >= (this.options.maxEventsPerType || 100)) {
      this.record.hoverEvents.shift();
    }
    this.record.hoverEvents.push(event);
  }

  private addElementInteraction(interaction: ElementInteraction): void {
    if (this.record.elementInteractions.length >= (this.options.maxEventsPerType || 100)) {
      this.record.elementInteractions.shift();
    }
    this.record.elementInteractions.push(interaction);
  }

  private updateHeatmapZone(click: ClickEvent): void {
    const zone = this.getHeatmapZone(click);
    
    const existingZone = this.record.metrics.mostClickedAreas.find(z => z.zone === zone);
    if (existingZone) {
      existingZone.count++;
    } else {
      this.record.metrics.mostClickedAreas.push({ zone, count: 1 });
    }
    
    // Keep sorted by count
    this.record.metrics.mostClickedAreas.sort((a, b) => b.count - a.count);
  }

  private getHeatmapZone(click: ClickEvent): HeatmapZone {
    const xPercent = (click.x / click.viewportWidth) * 100;
    const yPercent = (click.y / click.viewportHeight) * 100;
    
    let horizontal: 'left' | 'center' | 'right';
    let vertical: 'top' | 'middle' | 'bottom';
    
    if (xPercent < 33) horizontal = 'left';
    else if (xPercent < 66) horizontal = 'center';
    else horizontal = 'right';
    
    if (yPercent < 33) vertical = 'top';
    else if (yPercent < 66) vertical = 'middle';
    else vertical = 'bottom';
    
    return `${vertical}-${horizontal}` as HeatmapZone;
  }

  private updateMetrics(): void {
    // Calculate average time per page
    const completedVisits = this.record.pageVisits.filter(v => v.duration);
    if (completedVisits.length > 0) {
      const totalTime = completedVisits.reduce((sum, v) => sum + (v.duration || 0), 0);
      this.record.metrics.averageTimePerPage = Math.round(totalTime / completedVisits.length);
    }
    
    // Calculate total scroll distance
    let totalScrollDistance = 0;
    for (let i = 1; i < this.record.scrollEvents.length; i++) {
      totalScrollDistance += Math.abs(
        this.record.scrollEvents[i].scrollY - this.record.scrollEvents[i - 1].scrollY
      );
    }
    this.record.metrics.totalScrollDistance = totalScrollDistance;
  }
}


// Singleton instance management
let trackerInstance: BehaviorTracker | null = null;

export const initBehaviorTracker = (options: BehaviorTrackerOptions): BehaviorTracker => {
  if (trackerInstance) {
    trackerInstance.stop();
  }
  trackerInstance = new BehaviorTracker(options);
  trackerInstance.start();
  return trackerInstance;
};

export const getBehaviorTracker = (): BehaviorTracker | null => {
  return trackerInstance;
};

export const stopBehaviorTracker = (): void => {
  if (trackerInstance) {
    trackerInstance.stop();
    trackerInstance = null;
  }
};
