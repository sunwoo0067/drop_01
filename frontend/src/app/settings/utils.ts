export const toInt = (value: string, fallback: number) => {
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? fallback : parsed;
};

export const toFloat = (value: string, fallback: number) => {
    const parsed = parseFloat(value);
    return Number.isNaN(parsed) ? fallback : parsed;
};

export const parseNumberField = (value: string, isFloat = false) => {
    if (!value.trim()) {
        return null;
    }
    const parsed = isFloat ? parseFloat(value) : parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
};

export const parseCsvLine = (line: string) => {
    const result: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
        const char = line[i];
        if (char === "\"") {
            if (inQuotes && line[i + 1] === "\"") {
                current += "\"";
                i += 1;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }
        if (char === "," && !inQuotes) {
            result.push(current);
            current = "";
            continue;
        }
        current += char;
    }
    result.push(current);
    return result.map((value) => value.trim());
};

export const buildCategoryRowsFromCsv = (csvText: string) => {
    const rawLines = csvText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    if (rawLines.length === 0) {
        return [];
    }
    const headerIndex = rawLines.findIndex((line) => {
        const cells = parseCsvLine(line);
        return cells.length > 0 && !cells[0].startsWith("#");
    });
    if (headerIndex < 0) {
        return [];
    }
    const header = parseCsvLine(rawLines[headerIndex]).map((value) => value.toLowerCase());
    const keyMap: Record<string, string> = {
        category: "name",
        name: "name",
        min_sales: "min_sales",
        min_ctr: "min_ctr",
        min_views: "min_views",
        min_days_listed: "min_days_listed",
        min_repeat_purchase: "min_repeat_purchase",
        min_customer_retention: "min_customer_retention",
        min_revenue: "min_revenue",
        min_days_in_step2: "min_days_in_step2"
    };
    const indexes = header.map((label) => keyMap[label]).filter(Boolean);
    return rawLines.slice(headerIndex + 1).map((line) => {
        const values = parseCsvLine(line);
        if (values[0]?.startsWith("#")) {
            return null;
        }
        const row: Record<string, string> = {
            name: "",
            min_sales: "",
            min_ctr: "",
            min_views: "",
            min_days_listed: "",
            min_repeat_purchase: "",
            min_customer_retention: "",
            min_revenue: "",
            min_days_in_step2: ""
        };
        indexes.forEach((key, idx) => {
            row[key] = values[idx] ?? "";
        });
        return row;
    }).filter((row): row is Record<string, string> => Boolean(row && row.name.trim()));
};

export const collectCategoryRowErrors = (rows: Array<Record<string, string>>) => {
    const errors: string[] = [];
    const rowErrors: Record<number, string[]> = {};
    const fieldErrors: Record<number, Record<string, string>> = {};
    const seen = new Set<string>();
    rows.forEach((row, index) => {
        const pushRowError = (message: string) => {
            errors.push(message);
            rowErrors[index] = rowErrors[index] || [];
            rowErrors[index].push(message);
        };
        const pushFieldError = (field: string, message: string) => {
            fieldErrors[index] = fieldErrors[index] || {};
            if (!fieldErrors[index][field]) {
                fieldErrors[index][field] = message;
            }
        };
        const name = row.name.trim();
        if (!name) {
            const message = `카테고리명이 비어 있습니다 (행 ${index + 1})`;
            pushRowError(message);
            pushFieldError("name", message);
        } else if (seen.has(name)) {
            const message = `중복된 카테고리명입니다: ${name}`;
            pushRowError(message);
            pushFieldError("name", message);
        } else {
            seen.add(name);
        }
        const fields = [
            { key: "min_sales", isFloat: false },
            { key: "min_ctr", isFloat: true, min: 0, max: 1 },
            { key: "min_views", isFloat: false },
            { key: "min_days_listed", isFloat: false },
            { key: "min_repeat_purchase", isFloat: false },
            { key: "min_customer_retention", isFloat: true, min: 0, max: 1 },
            { key: "min_revenue", isFloat: false },
            { key: "min_days_in_step2", isFloat: false }
        ];
        fields.forEach(({ key, isFloat, min, max }) => {
            const raw = row[key] || "";
            if (!raw.trim()) {
                return;
            }
            const value = parseNumberField(raw, isFloat);
            const label = name || `행 ${index + 1}`;
            if (value === null) {
                const message = `${label}: ${key} 숫자 형식이 올바르지 않습니다.`;
                pushRowError(message);
                pushFieldError(key, message);
                return;
            }
            if (value < 0) {
                const message = `${label}: ${key}는 0 이상이어야 합니다.`;
                pushRowError(message);
                pushFieldError(key, message);
                return;
            }
            if (min !== undefined && value < min) {
                const message = `${label}: ${key}는 ${min} 이상이어야 합니다.`;
                pushRowError(message);
                pushFieldError(key, message);
            }
            if (max !== undefined && value > max) {
                const message = `${label}: ${key}는 ${max} 이하여야 합니다.`;
                pushRowError(message);
                pushFieldError(key, message);
            }
        });
    });
    return { errors, rowErrors, fieldErrors };
};

export const getSortedRows = (rows: Array<Record<string, string>>, key: string, direction: "asc" | "desc") => {
    const numericKeys = new Set([
        "min_sales",
        "min_ctr",
        "min_views",
        "min_days_listed",
        "min_repeat_purchase",
        "min_customer_retention",
        "min_revenue",
        "min_days_in_step2"
    ]);
    const next = [...rows];
    next.sort((a, b) => {
        const aVal = a[key] || "";
        const bVal = b[key] || "";
        if (numericKeys.has(key)) {
            const aNum = parseFloat(aVal);
            const bNum = parseFloat(bVal);
            const aValid = Number.isFinite(aNum);
            const bValid = Number.isFinite(bNum);
            if (!aValid && !bValid) {
                return 0;
            }
            if (!aValid) {
                return direction === "asc" ? 1 : -1;
            }
            if (!bValid) {
                return direction === "asc" ? -1 : 1;
            }
            return direction === "asc" ? aNum - bNum : bNum - aNum;
        }
        const comparison = aVal.localeCompare(bVal);
        return direction === "asc" ? comparison : -comparison;
    });
    return next;
};

export const buildCategoryAdjustedFromRows = (rows: Array<Record<string, string>>) => (
    rows.reduce<Record<string, Record<string, number>>>((acc, row) => {
        const name = row.name.trim();
        if (!name) {
            return acc;
        }
        const fields = [
            { key: "min_sales", isFloat: false },
            { key: "min_ctr", isFloat: true },
            { key: "min_views", isFloat: false },
            { key: "min_days_listed", isFloat: false },
            { key: "min_repeat_purchase", isFloat: false },
            { key: "min_customer_retention", isFloat: true },
            { key: "min_revenue", isFloat: false },
            { key: "min_days_in_step2", isFloat: false }
        ];
        const rules: Record<string, number> = {};
        fields.forEach(({ key, isFloat }) => {
            const value = parseNumberField(row[key] || "", isFloat);
            if (value !== null) {
                rules[key] = value;
            }
        });
        if (Object.keys(rules).length > 0) {
            acc[name] = rules;
        }
        return acc;
    }, {})
);
