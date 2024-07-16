function getImplicitDefault(type) {
    switch(type) {
    case 'string':
        return '';
    case 'integer':
    case 'number':
        return 0;
    case 'boolean':
        return false;
    case 'array':
        return [];
    case 'object':
        return {};
    default:
        return null;
    }
}

function compareWithDefaults(data, schema, path = '') {
    let nonDefaultValues = {};

    const properties = schema.properties || {};

    for (let key in properties) {
        if (Object.hasOwn(properties, key)) {
            const valueSchema = properties[key];
            const defaultValue = Object.hasOwn(valueSchema, 'default') ? valueSchema.default : getImplicitDefault(valueSchema.type);
            const dataKey = path ? `${path}.${key}` : key;

            if (valueSchema.type === 'object' && Object.hasOwn(data, key)) {
                const nestedNonDefaultValues = compareWithDefaults(data[key], valueSchema, dataKey);
                if (Object.keys(nestedNonDefaultValues).length > 0) {
                    nonDefaultValues = Object.assign(nonDefaultValues, nestedNonDefaultValues);
                }
            } else if (Object.hasOwn(data, key) && data[key] !== defaultValue) {
                nonDefaultValues[dataKey] = data[key];
            }
        }
    }

    return nonDefaultValues;
}

/* eslint-disable-next-line no-unused-vars */
function getConfigurationDefaults(schema) {
    let defaultValues = {};

    if (schema.type === 'object') {
        for (let key in schema.properties) {
            let valueSchema = schema.properties[key];
            if (valueSchema.type === 'object') {
                defaultValues[key] = getConfigurationDefaults(valueSchema);
            } else if (Object.hasOwn(valueSchema, 'default')) {
                defaultValues[key] = valueSchema.default;
            } else {
                defaultValues[key] = getImplicitDefault(valueSchema.type);
            }
        }
    }

    return defaultValues;
}

function getSchemaTitle(path, schema) {
    const keys = path.split('.');
    let currentSchema = schema;
    for (let key of keys) {
        if (currentSchema.properties && currentSchema.properties[key]) {
            currentSchema = currentSchema.properties[key];
        } else {
            return null;
        }
    }
    return currentSchema.title || null;
}

/* eslint-disable-next-line no-unused-vars */
function renderConfigurationAsTable(elemId, configuration, schema) {
    let tableHTML = `
        <table class="table table-striped">
        <thead>
            <tr>
            <th scope="col">Category</th>
            <th scope="col">Variable Title</th>
            <th scope="col">Value</th>
            <th scope="col">Variable key</th>
            </tr>
        </thead>
        <tbody>`;

    const flatDiffConfiguration = compareWithDefaults(configuration, schema);
    const categorizedConfs = {};

    for (let key in flatDiffConfiguration) {
        const prefix = key.split('.')[0];
        if (!categorizedConfs[prefix]) {
            categorizedConfs[prefix] = [];
        }
        categorizedConfs[prefix].push(key);
    }

    for (let category in categorizedConfs) {
        tableHTML += `
        <tr>
            <th scope="row">${category}</th>
            <td></td>
            <td></td>
            <td></td>
        </tr>`;

        for (let key of categorizedConfs[category]) {
            const value = flatDiffConfiguration[key];
            const title = getSchemaTitle(key, schema) || key;
            const variableName = key.split('.').pop();
            tableHTML += `
            <tr>
                <th scope="row"></th>
                <td>${title}</td>
                <td>${value}</td>
                <td>${variableName}</td>
            </tr>`;
        }
    }

    tableHTML += `
      </tbody>
    </table>`;

    document.getElementById(elemId).innerHTML = tableHTML;
}